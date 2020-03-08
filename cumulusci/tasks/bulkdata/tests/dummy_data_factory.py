import factory
import time
from cumulusci.tasks.bulkdata.factory_utils import ModuleDataFactory, Models


class GenerateDummyData(ModuleDataFactory):
    """Generate data based on test mapping.yml"""

    def make_records(self, num_records, factories, current_batch_num):
        factories.create_batch("ContactFactory", num_records, logger=self.logger)


class AccountFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Models.Account

    id = factory.Sequence(lambda i: i)
    Name = factory.Sequence(lambda i: f"Account {i} {time.time()}")
    BillingStreet = "Baker St."


class ContactFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Models.Contact
        exclude = ["account"]  # don't try to attach the account to the Contact directly

    id = factory.Sequence(lambda n: n + 1)
    account = factory.SubFactory(AccountFactory)  # create account automatically
    AccountId = factory.LazyAttribute(lambda o: o.account.id)
    FirstName = factory.Faker("first_name")
    LastName = factory.Sequence(lambda i: f"Contact {i} {time.time()}")
    Email = factory.Sequence(lambda i: f"Contact{i}.{time.time()}@example.com")
    MailingStreet = "Baker St."
