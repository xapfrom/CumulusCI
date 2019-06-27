from robot.api import SuiteVisitor


class PerformanceVisitor(SuiteVisitor):
    """This class reconfigures the test based on performance test parameters

    It will scan all tests looking for the keyword 'performance test
    settings'.  If found, it will pull out the number of iterations
    and then rewrite the internal model of the suite so that it runs
    the test case that many times.

    When it finds such a test, it adds "(Iteration <n>)" to the test
    name so that robot doesn't complain about duplicate test names. It
    also removes the 'performance test settings' keyword since it
    doesn't actually do anything.

    This class is designed to be used with the --prerunmodifier command line
    option to robot.

    DO NOT MERGE INTO MASTER!
    It is just a proof of concept, yo.
    """

    def start_suite(self, suite):
        tests = []
        for test in suite.tests:
            # at the moment, we require this to be the first keyword,
            # mainly becase I'm too lazy to do better.
            if test.keywords[0].name == "performance test settings":

                # Remove the keyword from the test and parse out the
                # options. I'm not sure if removing the keyword is the
                # right thing to do or not. We might want to leave it
                # in and define an actual keyword by that name which
                # is a no-op.
                kw = test.keywords.pop(0)
                options = self._parse_args(kw.args)

                # Replicate the test N times in the suite
                for i in range(int(options["iterations"])):
                    test_copy = test.deepcopy()
                    test_copy.name = "{} (iteration {})".format(test.name, i + 1)
                    tests.append(test_copy)
            else:
                tests.append(test)
        suite.tests = tests

    def _parse_args(self, args):
        """Convert a list of args in the form of ("foo=bar", "baz=burr")
        into a dictionary. Keys and values will be stripped of leading
        and trailing whitespace.
        """
        options = {}
        for arg in args:
            if "=" in arg:
                name, value = [s.strip() for s in arg.split("=", 1)]
            else:
                name = arg.strip()
                value = None
            options[name] = value
        return options
