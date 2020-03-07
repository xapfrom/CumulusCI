*** Settings ***
Library         DateTime
Resource        cumulusci/robotframework/Salesforce.robot
# Suite Teardown  Delete Session Records
Force Tags      performance

*** Keywords ***

Generate Data
    [Arguments]    ${count}

    Run Task Class   cumulusci.tasks.bulkdata.tests.dummy_data_factory.GenerateDummyData
    ...     num_records=${count}
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db

*** Test Cases ***

Perftest - Generate
    Generate Data   1000000

Perftest - Load 1000000
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db

Perftest - Delete
    Run Task Class   cumulusci.tasks.bulkdata.DeleteData
    ...     objects=Account,Contact

Perftest - Generate 2
    Generate Data   1000000

Perftest - Load 1000000 2
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db

Perftest - Delete 2
    Run Task Class   cumulusci.tasks.bulkdata.DeleteData
    ...     objects=Account,Contact

Perftest - Generate 3
    Generate Data   1000000

Perftest - Load 1000000 3
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db

Perftest - Delete 3
    Run Task Class   cumulusci.tasks.bulkdata.DeleteData
    ...     objects=Account,Contact

Perftest - Generate 4
    Generate Data   1000000

Perftest - Load 1000000 4
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db

Perftest - Delete 4
    Run Task Class   cumulusci.tasks.bulkdata.DeleteData
    ...     objects=Account,Contact
