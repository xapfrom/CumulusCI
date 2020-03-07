git clone https://github.com/SFDO-Tooling/CumulusCI.git
cd CumulusCI
git checkout feature/performance-tests
export PYTHONPATH=.
pip install -r requirements_dev.txt
pip install keychain.alt
alias cci="python -m cumulusci"
cci org connect abacus-perf-playground --default &
