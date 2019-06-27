*** Settings ***
Documentation
...  This contains a prototype of a performance test which
...  we want to run 20 times.
...
...  This requires that we use the prerunmodifer option and
...  pass it the file cumulusci/robotframework/PerformanceVisitor.py.
...  This is done in cumulusci.yml

*** Test Cases ***
Example perforance test
    performance test settings
    ...  iterations=20
    log  Zoom zoom!



    