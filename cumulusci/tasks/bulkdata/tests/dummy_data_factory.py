import factory
import time
from cumulusci.tasks.bulkdata.factory_utils import ModuleDataFactory, Models


class GenerateDummyData(ModuleDataFactory):
    """Generate data based on test mapping.yml"""

    def make_records(self, num_records, factories, current_batch_num):
        assert num_records % 4 == 0, "Use a batch size divisible by 4"
        print("A")
        self.logger.warning("A")
        factories.create_batch("ContactFactory", num_records // 2, logger=self.logger)
        self.logger.warning("B")
        factories["ContactFactory"].create_batch(num_records // 4)
        print("C")
        self.logger.warning("B")
        factories.create_batch("AccountFactory", num_records // 4, logger=self.logger)


class AccountFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Models.Account

    id = factory.Sequence(lambda i: i)
    Name = factory.Sequence(lambda i: f"Account {i} {time.time()}" % (i,))
    BillingStreet = "Baker St."


class ContactFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Models.Contact
        exclude = ["account"]  # don't try to attach the account to the Contact directly

    id = factory.Sequence(lambda n: n + 1)
    account = factory.SubFactory(AccountFactory)  # create account automatically
    AccountId = factory.LazyAttribute(lambda o: o.account.id)
    FirstName = factory.Faker("first_name")
    LastName = factory.Faker("last_name")
    LastName = factory.Sequence(lambda i: f"Contact {i} {time.time()}" % (i,))
    Email = factory.Faker("email", domain="example.com")
    MailingStreet = "Baker St."
