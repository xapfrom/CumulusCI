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

Load Data
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db
    ...     ignore_row_errors=True

Delete Data
    Run Task Class   cumulusci.tasks.bulkdata.DeleteData
    ...     objects=Account,Contact
    ...     ignore_row_errors=True

*** Test Cases ***

Perftest - Generate
    Generate Data   1000000

Perftest - Load 1000000
    Load Data

Perftest - Delete
    Delete Data

Perftest - Load 1000000 2
    Load Data

Perftest - Delete 2
    Delete Data

Perftest - Load 1000000 3
    Load Data

Perftest - Delete 3
    Delete Data

Perftest - Load 1000000 4
    Load Data

Perftest - Delete 4
    Delete Data
