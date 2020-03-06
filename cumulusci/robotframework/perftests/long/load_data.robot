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
    Generate Data   100000

Perftest - Load 100000
    Run Task Class   cumulusci.tasks.bulkdata.LoadData
    ...     mapping=cumulusci/tasks/bulkdata/tests/mapping_vanilla_sf.yml
    ...     database_url=sqlite:////tmp/data.db
