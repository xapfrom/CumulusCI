cci task run delete_data -o objects Account,Contact
cci task run delete_data -o objects Contact,Account
cci task run delete_data -o objects Account,Contact
cci task run delete_data -o objects Contact,Account
cci task run robot -o suites cumulusci/robotframework/perftests/long/ | tee /tmp/log.txt

