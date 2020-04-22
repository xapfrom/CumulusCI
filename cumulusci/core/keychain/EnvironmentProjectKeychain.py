import json
import os
from datetime import datetime

from cumulusci.core.config import ConnectedAppOAuthConfig
from cumulusci.core.config import OrgConfig
from cumulusci.core.config import ScratchOrgConfig
from cumulusci.core.config import ServiceConfig
from cumulusci.core.keychain import BaseProjectKeychain
from cumulusci.core.utils import import_global

scratch_org_class = os.environ.get("CUMULUSCI_SCRATCH_ORG_CLASS")
if scratch_org_class:
    scratch_org_factory = import_global(scratch_org_class)
else:
    scratch_org_factory = ScratchOrgConfig


class EnvironmentProjectKeychain(BaseProjectKeychain):
    """ A project keychain that stores org credentials in environment variables """

    encrypted = False
    org_var_prefix = "CUMULUSCI_ORG_"
    app_var = "CUMULUSCI_CONNECTED_APP"
    service_var_prefix = "CUMULUSCI_SERVICE_"

    def _get_env(self):
        """ loads the environment variables as unicode if ascii """
        env = {}
        for k, v in os.environ.items():
            k = k.decode() if isinstance(k, bytes) else k
            v = v.decode() if isinstance(v, bytes) else v
            env[k] = v
        return list(env.items())

    def _load_app(self):
        app = os.environ.get(self.app_var)
        if app:
            self.app = ConnectedAppOAuthConfig(json.loads(app))

    def _load_orgs(self):
        # TODO: This should be cached for performance
        #       but I believe that this method is also used
        #       to do re-loads after changes sometimes?
        #
        # It's called frequently so its worth investigation.
        for key, value in self._get_env():
            self._load_org_from_json(key, value)

    def _load_org_from_json(self, name, value):
        if name.startswith(self.org_var_prefix):
            try:
                org_config = json.loads(value)
            except json.decoder.JSONDecodeError:
                raise EnvironmentError(
                    f"Cannot load environment variable ${name} as JSON. Skipping."
                )
            if org_config.get("date_created"):
                org_config["date_created"] = datetime.fromisoformat(
                    org_config["date_created"]
                )
            org_name = name[len(self.org_var_prefix) :].lower()
            if org_config.get("scratch"):
                self.orgs[org_name] = scratch_org_factory(org_config, org_name)
            else:
                self.orgs[org_name] = OrgConfig(org_config, org_name)

    def _load_services(self):
        for key, value in self._get_env():
            if key.startswith(self.service_var_prefix):
                service_config = json.loads(value)
                service_name = key[len(self.service_var_prefix) :].lower()
                self._set_service(service_name, ServiceConfig(service_config))
