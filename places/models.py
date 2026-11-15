"""Pet-friendly places on the Explore map (stories: Use Reliable Location Data,
View Nearby Pet-Friendly Locations, View Dog Parks).

Dog parks come from NYC Parks' official "Dog Runs" dataset on NYC Open Data
(see the import_dog_runs command). NYC Open Data has no list of pet-friendly
cafés, stores or restaurants, so the PawPal team adds those in the admin. Every
place records where its information came from and when it was last checked.
"""

from datetime import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

# Longest explanation someone can add when reporting wrong information.
MAX_REPORT_LENGTH = 500

# Days in the order the hours are kept and shown (Figma: Mon first).
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def time_label(value):
    """ "08:00" -> "8 AM", "17:30" -> "5:30 PM"."""
    clock = datetime.strptime(value, "%H:%M")
    hour = clock.hour % 12 or 12
    minutes = f":{clock.minute:02d}" if clock.minute else ""
    return f"{hour}{minutes} {'AM' if clock.hour < 12 else 'PM'}"


def _as_time(value):
    return datetime.strptime(value, "%H:%M").time()


def _is_open_at(day_hours, moment):
    """Whether one day's hours ({"open", "close"}) include `moment` (a time) on
    that day. Hours that close at or before they open run past midnight."""
    opens, closes = _as_time(day_hours["open"]), _as_time(day_hours["close"])
    if closes <= opens:
        return moment >= opens
    return opens <= moment < closes


def _after_midnight(day_hours, moment):
    """Whether yesterday's hours still cover `moment` early this morning."""
    opens, closes = _as_time(day_hours["open"]), _as_time(day_hours["close"])
    return closes <= opens and moment < closes


class PlaceQuerySet(models.QuerySet):
    def shown(self):
        """Places people can see: not hidden by an admin or dropped by the source."""
        return self.filter(is_active=True)


class Place(models.Model):
    class Category(models.TextChoices):
        # Labels match the Figma badges.
        DOG_PARK = "dog_park", "Dog park"
        CAFE = "cafe", "Café"
        PET_STORE = "pet_store", "Pet store"
        RESTAURANT = "restaurant", "Restaurant"

    class Source(models.TextChoices):
        NYC_PARKS = "nyc_parks", "NYC Parks on NYC Open Data"
        PAWPAL = "pawpal", "the PawPal team"

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    # Street address or cross streets, e.g. "214 7th Ave" or "Prospect Park W & 3rd St".
    address = models.CharField(max_length=200, blank=True)
    # Shown instead of the address when there is none (NYC Parks lists none).
    neighborhood = models.CharField(max_length=100, blank=True)
    borough = models.CharField(max_length=20, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    # Hours written out, for places without day-by-day hours.
    hours = models.CharField(
        max_length=80, blank=True, help_text="For example: Open daily 8 AM – 6 PM"
    )
    # Day-by-day hours set on the admin page (Figma "Manage Pet-Friendly
    # Location"): 7 entries, Monday first, each {"open": "08:00", "close":
    # "17:00"} or null when closed that day. Empty when not listed.
    weekly_hours = models.JSONField(default=list, blank=True)
    features = models.TextField(
        blank=True,
        help_text="What makes it pet-friendly, one per line. "
        "For example: Water bowls and treats",
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.PAWPAL
    )
    # The place's id in the source dataset, so a new import updates it.
    source_id = models.CharField(max_length=64, blank=True)
    # When the information was last checked against its source.
    checked_on = models.DateField(null=True, blank=True)
    # Unticked when an admin hides it or the source no longer lists it.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # When an admin last changed its details. Imports from NYC Open Data leave
    # places an admin edited alone, so a fix isn't undone by the next import.
    edited_at = models.DateTimeField(null=True, blank=True)

    objects = PlaceQuerySet.as_manager()

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=~Q(source_id=""),
                name="one_place_per_source_id",
            )
        ]

    def __str__(self):
        return self.name

    def feature_list(self):
        return [line.strip() for line in self.features.splitlines() if line.strip()]

    def place_line(self):
        """ "214 7th Ave, Brooklyn", or "Park Slope, Brooklyn" when there's no address.

        The borough is added once, even when the address already ends with it.
        """
        first = self.address or self.neighborhood
        if not first:
            return self.borough
        if self.borough and not first.rstrip().lower().endswith(self.borough.lower()):
            return f"{first}, {self.borough}"
        return first

    def week(self, now=None):
        """The day-by-day hours for the admin page, Monday first: name,
        "8 AM – 5 PM" or None when closed, and whether it's today."""
        if not self.weekly_hours:
            return []
        today = timezone.localtime(now).weekday()
        return [
            {
                "name": name,
                "hours": (
                    f"{time_label(day['open'])} – {time_label(day['close'])}"
                    if day
                    else None
                ),
                "is_today": index == today,
            }
            for index, (name, day) in enumerate(zip(DAYS, self.weekly_hours))
        ]

    def is_open_now(self, now=None):
        """True or False from the day-by-day hours; None when they aren't listed."""
        if not self.weekly_hours:
            return None
        local = timezone.localtime(now)
        today = self.weekly_hours[local.weekday()]
        yesterday = self.weekly_hours[(local.weekday() - 1) % 7]
        moment = local.time()
        return bool(
            (today and _is_open_at(today, moment))
            or (yesterday and _after_midnight(yesterday, moment))
        )

    def hours_line(self, now=None):
        """ "8 AM – 6 PM" -> "Open today 8 AM – 6 PM", as in the design.

        Hours written as a sentence ("Open daily 6 AM – 1 AM") are shown as is.
        """
        if self.weekly_hours:
            today = self.week(now)[timezone.localtime(now).weekday()]
            if today["hours"]:
                return f"Open today {today['hours']}"
            return "Closed today"
        hours = self.hours.strip()
        if hours[:1].isdigit():
            return f"Open today {hours}"
        return hours

    def directions_url(self):
        return (
            "https://www.google.com/maps/dir/?api=1&destination="
            f"{self.latitude},{self.longitude}"
        )

    def report_url(self):
        return reverse("places:report", args=[self.pk])


class PlaceReport(models.Model):
    """Someone told us a place's information is wrong ("Report wrong info").

    Admins see these on the Reports page, one row per place (Figma "Pet-Friendly
    Places Report"), and mark them resolved once the place is fixed.
    """

    class Reason(models.TextChoices):
        # Labels match the Figma "Report wrong info" pop-up.
        WRONG_HOURS = "wrong_hours", "Wrong hours"
        WRONG_ADDRESS = "wrong_address", "Wrong address"
        CLOSED = "closed", "Permanently closed"
        NOT_PET_FRIENDLY = "not_pet_friendly", "Not pet-friendly"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    # Lets the Reports page tell these apart from review and message reports.
    is_place_report = True
    kind = "place"

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="place_reports",
    )
    reason = models.CharField(
        max_length=20, choices=Reason.choices, default=Reason.OTHER
    )
    details = models.TextField(max_length=MAX_REPORT_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    # Filled in when an admin marks the report resolved.
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="place_reports_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.place}: {self.details[:40]}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    def group(self):
        """The reports shown together with this one: the place's open reports,
        or the ones resolved with it."""
        reports = PlaceReport.objects.filter(place_id=self.place_id).select_related(
            "reporter"
        )
        if self.is_open:
            return reports.filter(status=self.Status.OPEN)
        return reports.filter(status=self.Status.RESOLVED, resolved_at=self.resolved_at)

    def resolve(self, admin):
        """Close every open report on this place. Returns how many closed."""
        return PlaceReport.objects.filter(
            place_id=self.place_id, status=self.Status.OPEN
        ).update(
            status=self.Status.RESOLVED, resolved_by=admin, resolved_at=timezone.now()
        )
