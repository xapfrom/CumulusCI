rm /tmp/data.db
cci task run delete_data -o objects Account,Contact
cci task run robot -o suites cumulusci/robotframework/perftests/long/ | tee /tmp/log.txt

