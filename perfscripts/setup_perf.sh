git clone https://github.com/SFDO-Tooling/CumulusCI.git
cd CumulusCI
git checkout feature/refactor_bulk_api__performance_test
export PYTHONPATH=.
pip install -r requirements.txt
pip install keyrings.alt
alias cci="python -m cumulusci"
cci org connect abacus-perf-playground --default &
