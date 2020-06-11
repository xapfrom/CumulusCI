from typing import Optional
import base64
import enum
import hashlib
import io
import json
import os
import pathlib
import zipfile

from pydantic import BaseModel

from cumulusci.core.exceptions import DependencyLookupError
from cumulusci.core.exceptions import PackageUploadFailure
from cumulusci.core.exceptions import TaskOptionsError
from cumulusci.core.flowrunner import FlowCoordinator
from cumulusci.core.utils import process_bool_arg
from cumulusci.salesforce_api.package_zip import MetadataPackageZipBuilder
from cumulusci.tasks.salesforce import BaseSalesforceApiTask
from cumulusci.utils import download_extract_github


class PackageTypeEnum(str, enum.Enum):
    managed = "Managed"
    unlocked = "Unlocked"


class VersionTypeEnum(str, enum.Enum):
    major = "major"
    minor = "minor"
    patch = "patch"


class PackageConfig(BaseModel):
    name: str
    description: str = ""
    package_type: PackageTypeEnum = PackageTypeEnum.managed
    namespace: Optional[str]
    branch: str = None
    version_name: str
    version_type: VersionTypeEnum = VersionTypeEnum.minor


class CreatePackageVersion(BaseSalesforceApiTask):
    """Creates a new second-generation package version.

    If a package named ``package_name`` does not yet exist in the Dev Hub, it will be created.
    """

    task_options = {
        "package_name": {"description": "Name of package"},
        "package_type": {"description": "Package type (unlocked or managed)"},
        "namespace": {"description": "Package namespace"},
        "version_name": {"description": "Version name"},
        "version_type": {
            "description": "The part of the version number to increment. "
            "Options are major, minor, patch.  Defaults to minor"
        },
        "dependency_org": {
            "description": "The org name of the org to use for project dependencies lookup. If not provided, a scratch org will be created with the org name 2gp_dependencies."
        },
        "skip_validation": {
            "description": "If true, skip validation of the package version. Default: false. "
            "Skipping validation creates packages more quickly, but they cannot be promoted for release."
        },
    }

    def _init_options(self, kwargs):
        super()._init_options(kwargs)

        source_format = self.project_config.project__package__source_format or "sfdx"
        # @@@ use default package from sfdx-project.json
        self.source_path = "src" if source_format == "mdapi" else "force-app"
        self.package_config = PackageConfig(
            name=self.options.get("name") or self.project_config.project__package__name,
            package_type=self.options.get("package_type")
            or self.project_config.project__package__type,
            namespace=self.options.get("namespace")
            or self.project_config.project__package__namespace,
            branch=self.project_config.repo_branch,
            version_name=self.options.get("version_name") or "Release",
            version_type=self.options.get("version_type") or "minor",
        )
        self.options["skip_validation"] = process_bool_arg(
            self.options.get("skip_validation", False)
        )

    def _run_task(self):
        """Creates a new 2GP package version.

        1. Create package if not found in Dev Hub.
        2. Request creation of package version.
        3. Wait for completion.
        4. Collect package information as return values.
        """
        # find existing package in Dev Hub, or create one if necessary
        self.package_id = self._get_or_create_package(self.package_config)
        self.return_values["package_id"] = self.package_id

        # submit request to create package version
        package_zip = MetadataPackageZipBuilder(
            path=self.source_path, name=self.package_config.name, logger=self.logger
        ).as_bytes()
        self.request_id = self._create_version_request(
            self.package_id, self.package_config, package_zip
        )
        self.return_values["request_id"] = self.request_id

        # wait for request to complete
        self._poll()
        self.return_values["package2_version_id"] = self.package_version_id

        # get the new version number from Package2Version
        res = self.tooling.query(
            "SELECT MajorVersion, MinorVersion, PatchVersion, BuildNumber, SubscriberPackageVersionId FROM Package2Version WHERE Id='{}' ".format(
                self.package_version_id
            )
        )
        package2_version = res["records"][0]
        self.return_values["subscriber_package_version_id"] = package2_version[
            "SubscriberPackageVersionId"
        ]
        self.return_values["version_number"] = self._get_version_number(
            package2_version
        )

        # get the new version's dependencies from SubscriberPackageVersion
        res = self.tooling.query(
            "SELECT Dependencies FROM SubscriberPackageVersion "
            f"WHERE Id='{package2_version['SubscriberPackageVersionId']}'"
        )
        subscriber_version = res["records"][0]
        self.return_values["dependencies"] = subscriber_version["Dependencies"]

        # @@@ better output format
        self.logger.info("Return Values: {}".format(self.return_values))

    def _get_or_create_package(self, package_config: PackageConfig):
        """Find or create the Package2

        Checks the Dev Hub for an existing, non-deprecated 2GP package
        with matching name, type, and namespace.
        """
        message = f"Checking for existing {package_config.package_type} Package named {package_config.name}"
        query = f"SELECT Id FROM Package2 WHERE IsDeprecated = FALSE AND ContainerOptions='{package_config.package_type}' AND Name='{package_config.name}'"
        if package_config.namespace:
            query += f" AND NamespacePrefix='{package_config.namespace}'"
            message += f" with namespace {package_config.namespace}"
        else:
            query += " AND NamespacePrefix=null"
        self.logger.info(message)
        res = self.tooling.query(query)
        # @@@ catch error if dev hub isn't enabled for 2gp
        if res["size"] > 1:
            raise TaskOptionsError(
                f"Found {res['size']} packages with the same name, namespace, and package_type"
            )
        if res["size"] == 1:
            package_id = res["records"][0]["Id"]
            self.logger.info(f"Found {package_id}")
            return package_id

        self.logger.info("No existing package found, creating the package")
        Package2 = self._get_tooling_object("Package2")
        package = Package2.create(
            {
                "ContainerOptions": package_config.package_type,
                "Name": package_config.name,
                "Description": package_config.description,
                "NamespacePrefix": package_config.namespace,
            }
        )
        return package["id"]

    def _create_version_request(self, package_id, package_config, package_zip):
        # Prepare the VersionInfo file
        version_bytes = io.BytesIO()
        version_info = zipfile.ZipFile(version_bytes, "w", zipfile.ZIP_DEFLATED)
        try:

            # Add the package.zip
            package_hash = hashlib.blake2b(package_zip).hexdigest()
            version_info.writestr("package.zip", package_zip)

            # Check for an existing package with the same contents
            res = self.tooling.query(
                "SELECT Id "
                "FROM Package2VersionCreateRequest "
                "WHERE Package2Id = '{}' "
                "AND Status != 'Error' "
                "AND Tag = 'hash:{}'".format(package_id, package_hash)
            )
            if res["size"] > 0:
                self.logger.info(
                    "Found existing request for package with the same metadata.  Using existing package."
                )
                return res["records"][0]["Id"]

            # Create the package2-descriptor.json contents and write to version_info
            # @@@ what if it's based on an older version?
            # - specify base version
            version_number = self._get_next_version_number(
                package_id, package_config.version_type
            )
            package_descriptor = {
                "ancestorId": "",  # @@@ need to add this for Managed 2gp
                "id": package_id,
                "path": "",
                "versionName": package_config.version_name,
                "versionNumber": version_number,
            }

            # Get the dependencies for the package
            is_dependency = package_config is not self.package_config
            if not is_dependency:
                self.logger.info("Determining dependencies for package")
                dependencies = self._get_dependencies()
                if dependencies:
                    package_descriptor["dependencies"] = dependencies

            # Finish constructing the request
            version_info.writestr(
                "package2-descriptor.json", json.dumps(package_descriptor)
            )
        finally:
            version_info.close()
        version_info = base64.b64encode(version_bytes.getvalue()).decode("utf-8")
        Package2CreateVersionRequest = self._get_tooling_object(
            "Package2VersionCreateRequest"
        )
        request = {
            "Branch": package_config.branch,
            "Package2Id": package_id,
            "SkipValidation": self.options["skip_validation"],
            "Tag": f"hash:{package_hash}",
            "VersionInfo": version_info,
        }
        # @@@ log
        response = Package2CreateVersionRequest.create(request)
        return response["id"]

    def _get_next_version_number(self, package_id, version_type: VersionTypeEnum):
        """Predict the next package version.

        Given a package id and version type (major/minor/patch),
        we query the Dev Hub org for the highest version, then increment.
        """
        res = self.tooling.query(
            "SELECT MajorVersion, MinorVersion, PatchVersion, BuildNumber, IsReleased "
            "FROM Package2Version "
            f"WHERE Package2Id='{package_id}' "
            "ORDER BY MajorVersion DESC, MinorVersion DESC, PatchVersion DESC, BuildNumber DESC "
            "LIMIT 1"
        )
        if res["size"] == 0:  # No existing version
            version_parts = {
                "MajorVersion": 1 if version_type == VersionTypeEnum.major else 0,
                "MinorVersion": 1 if version_type == VersionTypeEnum.minor else 0,
                "PatchVersion": 1 if version_type == VersionTypeEnum.patch else 0,
                "BuildNumber": "NEXT",
            }
            return self._get_version_number(version_parts)
        last_version = res["records"][0]
        version_parts = {
            "MajorVersion": last_version["MajorVersion"],
            "MinorVersion": last_version["MinorVersion"],
            "PatchVersion": last_version["PatchVersion"],
            "BuildNumber": "NEXT",
        }
        if last_version["IsReleased"] is True:
            if version_type == VersionTypeEnum.major:
                version_parts["MajorVersion"] += 1
                version_parts["MinorVersion"] = 0
                version_parts["PatchVersion"] = 0
            if version_type == VersionTypeEnum.minor:
                version_parts["MinorVersion"] += 1
                version_parts["PatchVersion"] = 0
            elif version_type == VersionTypeEnum.patch:
                version_parts["PatchVersion"] += 1
        return self._get_version_number(version_parts)

    def _get_version_number(self, version):
        """Format version fields from Package2Version as a version number."""
        return "{MajorVersion}.{MinorVersion}.{PatchVersion}.{BuildNumber}".format(
            **version
        )

    def _get_dependencies(self):
        """Resolve dependencies into SubscriberPackageVersionIds (04t prefix)"""
        dependencies = self.project_config.get_static_dependencies()

        # If any dependencies are expressed as a 1gp namespace + version,
        # we need to convert those to 04t package version ids,
        # for which we need an org with the packages installed.
        if self._has_1gp_namespace_dependency(dependencies):
            org = self._get_dependency_org()
            dependencies = org.resolve_04t_dependencies(dependencies)

        # Convert dependencies to correct format for Package2VersionCreateRequest
        dependencies = self._convert_project_dependencies(dependencies)

        # Build additional packages for local unpackaged/pre
        dependencies = self._get_unpackaged_pre_dependencies(dependencies)

        return dependencies

    def _has_1gp_namespace_dependency(self, project_dependencies):
        """Returns true if any dependencies are specified using a namespace rather than 04t"""
        for dependency in project_dependencies:
            if "namespace" in dependency:
                return True
            if "dependencies" in dependency:
                if self._has_1gp_namespace_dependency(dependency["dependencies"]):
                    return True
        return False

    def _get_dependency_org(self):
        """Get a scratch org that we can use to look up subscriber package version ids.

        If the `dependency_org` option is specified, use it.
        Otherwise create a new org named `2gp_dependencies` and run the `dependencies` flow.
        """
        org_name = self.options.get("dependency_org")
        if org_name:
            org = self.project_config.keychain.get_org(org_name)
        else:
            org_name = "2gp_dependencies"
            if org_name not in self.project_config.keychain.orgs:
                self.project_config.keychain.create_scratch_org(
                    "2gp_dependencies", "dev"
                )

            org = self.project_config.keychain.get_org("2gp_dependencies")
            if org.created and org.expired:
                self.logger.info(
                    "Recreating expired scratch org named 2gp_dependencies to resolve package dependencies"
                )
                org.create_org()
                self.project_config.keychain.set_org("2gp_dependencies", org)
            elif org.created:
                self.logger.info(
                    "Using existing scratch org named 2gp_dependencies to resolve dependencies"
                )
            else:
                self.logger.info(
                    "Creating a new scratch org with the name 2gp_dependencies to resolve dependencies"
                )

            self.logger.info(
                "Running the dependencies flow against the 2gp_dependencies scratch org"
            )
            coordinator = FlowCoordinator(
                self.project_config, self.project_config.get_flow("dependencies")
            )
            coordinator.run(org)

        return org

    def _convert_project_dependencies(self, dependencies):
        """Convert dependencies into the format expected by Package2VersionCreateRequest.

        For dependencies expressed as a github repo subfolder, build an unlocked package from that.
        """
        new_dependencies = []
        # @@@ why are unpackaged dependencies getting added first?
        for dependency in dependencies:
            if dependency.get("dependencies"):
                new_dependencies.extend(
                    self._convert_project_dependencies(dependency["dependencies"])
                )

            new_dependency = {}
            if dependency.get("version_id"):
                if "namespace" in dependency:
                    self.logger.info(
                        f"Adding dependency {dependency['namespace']}@{dependency['version']} "
                        f"with id {dependency['version_id']}"
                    )
                else:
                    self.logger.info(
                        f"Adding dependency with id {dependency['version_id']}"
                    )
                new_dependency["subscriberPackageVersionId"] = dependency["version_id"]

            elif dependency.get("repo_name"):
                if dependency.get("subfolder", "").startswith("unpackaged/post"):
                    continue
                version_id = self._create_unlocked_package_from_github(dependency)
                self.logger.info(
                    "Adding dependency {}/{} {} with id {}".format(
                        dependency["repo_owner"],
                        dependency["repo_name"],
                        dependency["subfolder"],
                        version_id,
                    )
                )
                new_dependency["subscriberPackageVersionId"] = version_id

            else:
                raise DependencyLookupError(
                    f"Unable to convert dependency: {dependency}"
                )

            new_dependencies.append(new_dependency)

        return new_dependencies

    def _get_unpackaged_pre_dependencies(self, dependencies):
        """Create package for unpackaged/pre metadata, if necessary
        """
        path = pathlib.Path("unpackaged", "pre")
        if not path.exists():
            return dependencies

        for item in path.iterdir():
            if not item.is_dir():
                continue
        for item_path in sorted(os.listdir(path)):
            version_id = self._create_unlocked_package_from_local(item_path)
            self.logger.info(
                "Adding dependency {}/{} {} with id {}".format(
                    self.project_config.repo_owner,
                    self.project_config.repo_name,
                    item_path,
                    version_id,
                )
            )
            dependencies.append({"subscriberPackageVersionId": version_id})

        return dependencies

    def _create_unlocked_package_from_github(self, dependency):
        gh_for_repo = self.project_config.get_github_api(
            dependency["repo_owner"], dependency["repo_name"]
        )
        zip_src = download_extract_github(
            gh_for_repo,
            dependency["repo_owner"],
            dependency["repo_name"],
            dependency["subfolder"],
            ref=dependency.get("ref"),
        )
        package_zip = MetadataPackageZipBuilder.from_zipfile(
            zip_src, options=dependency, logger=self.logger
        ).as_bytes()

        package_config = PackageConfig(
            name="{repo_owner}/{repo_name} {subfolder}".format(**dependency),
            version_name="{{ version }}",  # @@@ substitute
            package_type="Unlocked",
            # Ideally we'd do this without a namespace,
            # but it needs to match the dependent package
            namespace=self.package_config.namespace,
        )
        package_id = self._get_or_create_package(package_config)
        self.request_id = self._create_version_request(
            package_id, package_config, package_zip
        )

        self._poll()
        self.poll_complete = False  # @@@ also reset interval
        res = self.tooling.query(
            "SELECT SubscriberPackageVersionId FROM Package2Version "
            f"WHERE Id='{self.package_version_id}'"
        )
        package2_version = res["records"][0]
        return package2_version["SubscriberPackageVersionId"]

    def _create_unlocked_package_from_local(self, path):
        """Create an unlocked package version from a local directory."""
        self.logger.info("Creating package for dependencies in {}".format(path))
        package_name = (
            f"{self.project_config.repo_owner}/{self.project_config.repo_name} {path}"
        )
        package_zip = MetadataPackageZipBuilder(
            path=path, name=package_name, logger=self.logger
        ).as_bytes()
        package_config = PackageConfig(
            name=package_name,
            version_name="{{ version }}",  # @@@ substitute
            package_type="Unlocked",
            # Ideally we'd do this without a namespace,
            # but it needs to match the dependent package
            namespace=self.package_config.namespace,
        )
        package_id = self._get_or_create_package(package_config)
        self.request_id = self._create_version_request(
            package_id, package_config, package_zip
        )
        self._poll()
        self.poll_complete = False  # @@@ also reset interval
        res = self.tooling.query(
            "SELECT SubscriberPackageVersionId FROM Package2Version "
            f"WHERE Id='{self.package_version_id}'"
        )
        package2_version = res["records"][0]
        return package2_version["SubscriberPackageVersionId"]

    def _poll_action(self):
        """Check if Package2VersionCreateRequest has completed."""
        res = self.tooling.query(
            f"SELECT Id, Status, Package2VersionId FROM Package2VersionCreateRequest WHERE Id = '{self.request_id}'"
        )
        request = res["records"][0]
        if request["Status"] == "Success":
            self.logger.info("[Success]: Package creation successful")
            self.poll_complete = True
            self.package_version_id = request["Package2VersionId"]
        elif request["Status"] == "Error":
            self.logger.error("[Error]: Package creation failed with error:")
            res = self.tooling.query(
                "SELECT Message FROM Package2VersionCreateRequestError "
                f"WHERE ParentRequestId = '{request['Id']}'"
            )
            errors = []
            if res["size"] > 0:
                for error in res["records"]:
                    errors.append(error["Message"])
                    self.logger.error(error["Message"])
            raise PackageUploadFailure("\n".join(errors))
        elif request["Status"] in ("Queued", "InProgress"):
            self.logger.info(
                f"[{request['Status']}: Checking status of Package2VersionCreateRequest {request['Id']}"
            )