"""Find caregivers filtered by when they're free (?date=&start_time=&end_time=).

The date/time fields are hidden on the page until there's a Figma design, but
the search still applies the filter from the address."""

from datetime import date, time, timedelta

from caregivers.models import CaregiverAvailability
from caregivers.search import available_during, searchable_caregivers

from .test_search import NYU, URL, SearchTestData

DAY = date.today() + timedelta(days=3)


class AvailabilitySearchTests(SearchTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        CaregiverAvailability.objects.create(
            caregiver=cls.village, date=DAY, start_time=time(9), end_time=time(13)
        )
        CaregiverAvailability.objects.create(
            caregiver=cls.midtown, date=DAY, start_time=time(11), end_time=time(12)
        )

    def search(self, **params):
        self.client.force_login(self.owner)
        return self.client.get(URL, params)

    def names(self, response):
        return [c.name for c in response.context["caregivers"]]

    def at(self, start, end, day=DAY, **extra):
        return {
            "date": day.isoformat(),
            "start_time": start,
            "end_time": end,
            **extra,
        }

    def test_only_caregivers_free_for_the_whole_time_are_listed(self):
        self.assertEqual(
            self.names(self.search(**self.at("10:00", "12:00"))), ["Chloe"]
        )
        self.assertEqual(
            self.names(self.search(**self.at("11:00", "12:00"))), ["Alicia", "Chloe"]
        )

    def test_works_with_a_location(self):
        response = self.search(
            **self.at("11:00", "12:00", address="70 Washington Square South", **NYU)
        )
        self.assertEqual(self.names(response), ["Chloe", "Alicia"])
        response = self.search(
            **self.at("10:00", "12:00", address="70 Washington Square South", **NYU)
        )
        self.assertEqual(self.names(response), ["Chloe"])

    def test_no_one_free_says_so(self):
        response = self.search(**self.at("10:00", "12:00", day=DAY + timedelta(days=1)))
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "are free at that time")
        self.assertContains(response, "Try another date or time.")
        self.assertNotContains(response, "No caregivers on PawPal yet")

    def test_incomplete_or_invalid_times_are_ignored_with_a_notice(self):
        everyone = self.names(self.search())
        cases = {
            "Choose a date, start time, and end time": {"date": DAY.isoformat()},
            "Please choose a valid date and time range": self.at("12:00", "10:00"),
        }
        for notice, params in cases.items():
            response = self.search(**params)
            self.assertContains(response, notice)
            self.assertEqual(self.names(response), everyone)
        response = self.search(date="not-a-date", start_time="10:00", end_time="11:00")
        self.assertContains(response, "Please choose a valid date and time range")

    def test_fields_are_hidden_but_the_filter_is_kept_when_searching_again(self):
        response = self.search(**self.at("10:00", "12:00"))
        self.assertNotContains(response, 'id="availability-date"')
        self.assertContains(response, f'name="date" value="{DAY.isoformat()}"')
        self.assertContains(response, 'name="start_time" value="10:00"')
        self.assertContains(response, 'name="end_time" value="12:00"')
        self.assertEqual(response.context["query_without_availability"], "")

    def test_clear_link_keeps_the_rest_of_the_search(self):
        response = self.search(**self.at("10:00", "12:00", distance=3))
        self.assertEqual(response.context["query_without_availability"], "distance=3")

    def test_available_during(self):
        everyone = searchable_caregivers(self.owner)
        self.assertEqual(
            list(available_during(everyone, DAY, time(9), time(13))), [self.village]
        )
        self.assertEqual(list(available_during(everyone, DAY, time(12), time(14))), [])
