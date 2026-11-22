"""#105 Manage Community Guidelines, as in Kat's Figma: admins add, edit and
remove the numbered rules on their own page (from the Forum in Explore), and
everyone else reads them in a popup on the Forum."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from forum.models import GuidelineRule, guidelines_updated_at

from .test_browse import LIST_URL, ForumTestData, detail_url

User = get_user_model()
PAGE = reverse("forum:guidelines")
ADD = reverse("forum:add_rule")
DEFAULTS = [
    "Be kind",
    "Keep it about pets",
    "No spam or ads",
    "Keep personal info private",
    "Play by the rules",
]


def edit_url(rule):
    return reverse("forum:edit_rule", args=[rule.pk])


def remove_url(rule):
    return reverse("forum:remove_rule", args=[rule.pk])


class GuidelinesTestData(ForumTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_user(
            "ada", password="pw-12345!", is_staff=True, first_name="Ada"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def rule(self, title):
        return GuidelineRule.objects.get(title=title)

    def shown_titles(self):
        return list(GuidelineRule.objects.shown().values_list("title", flat=True))


class DefaultRulesTests(TestCase):
    def test_starts_with_the_five_figma_rules_in_order(self):
        rules = list(GuidelineRule.objects.shown())
        self.assertEqual([r.title for r in rules], DEFAULTS)
        self.assertEqual([r.position for r in rules], [1, 2, 3, 4, 5])
        self.assertEqual(str(rules[0]), "Be kind")

    def test_last_updated_is_empty_without_rules(self):
        GuidelineRule.objects.all().delete()
        self.assertIsNone(guidelines_updated_at())


class AccessTests(GuidelinesTestData):
    def test_logged_out_visitors_go_to_log_in(self):
        self.client.logout()
        response = self.client.get(PAGE)
        self.assertRedirects(response, f"{reverse('login')}?next={PAGE}")

    def test_only_admins_can_manage(self):
        rule = self.rule("Be kind")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(PAGE).status_code, 403)
        data = {"title": "New", "text": "Text"}
        self.assertEqual(self.client.post(ADD, data).status_code, 403)
        self.assertEqual(self.client.post(edit_url(rule), data).status_code, 403)
        self.assertEqual(self.client.post(remove_url(rule)).status_code, 403)
        self.assertEqual(self.shown_titles(), DEFAULTS)

    def test_changes_need_post(self):
        rule = self.rule("Be kind")
        for url in (ADD, edit_url(rule), remove_url(rule)):
            self.assertEqual(self.client.get(url).status_code, 405)


class PageTests(GuidelinesTestData):
    def test_lists_the_numbered_rules(self):
        response = self.client.get(PAGE)
        self.assertContains(response, '<h1 class="guidelines-title">Community')
        self.assertContains(
            response, "Everyone sees these in the Forum. Only admins can change them."
        )
        self.assertContains(response, "Last updated ")
        self.assertContains(response, f'href="{LIST_URL}"')
        self.assertEqual(response.context["rules"], list(GuidelineRule.objects.shown()))
        for number, title in enumerate(DEFAULTS, start=1):
            rule = self.rule(title)
            self.assertContains(response, f'href="?edit={rule.pk}"')
            self.assertContains(response, f'href="?remove={rule.pk}"')
        self.assertContains(response, 'class="guideline-number" aria-hidden="true">5<')
        self.assertContains(response, 'href="?add=1"')
        # The admin menu shows Explore, as for the forum.
        self.assertContains(
            response, f'href="{reverse("places:manage")}" class="active">Explore'
        )

    def test_empty_guidelines(self):
        GuidelineRule.objects.all().delete()
        response = self.client.get(PAGE)
        self.assertContains(response, "No rules yet.")
        self.assertNotContains(response, "Last updated")
        self.assertContains(response, 'href="?add=1"')


class EditTests(GuidelinesTestData):
    def test_edit_opens_the_rule_as_a_form(self):
        rule = self.rule("No spam or ads")
        response = self.client.get(PAGE, {"edit": rule.pk})
        self.assertEqual(response.context["editing"], rule)
        self.assertContains(response, f'action="{edit_url(rule)}"')
        self.assertContains(response, 'value="No spam or ads"')
        self.assertContains(response, "Don’t post deals, links to sell things")
        self.assertContains(response, ">Cancel</a>")
        # Figma: no "Add rule" while a rule is open.
        self.assertNotContains(response, 'href="?add=1"')

    def test_unknown_edit_is_ignored(self):
        response = self.client.get(PAGE, {"edit": "999"})
        self.assertIsNone(response.context["editing"])
        self.assertIsNone(response.context["form"])

    def test_saving_an_edit(self):
        rule = self.rule("No spam or ads")
        data = {
            "title": " No spam or ads ",
            "text": "Only share links to trusted pet shops or vets.",
        }
        response = self.client.post(edit_url(rule), data, follow=True)
        self.assertRedirects(response, f"{PAGE}?done=saved")
        self.assertContains(response, "Rule saved. Users can now see the update.")
        rule.refresh_from_db()
        self.assertEqual(rule.title, "No spam or ads")
        self.assertEqual(rule.text, data["text"])
        self.assertEqual(rule.position, 3)

    def test_saving_without_changes_keeps_last_updated(self):
        rule = self.rule("Be kind")
        before = timezone.now() - timedelta(days=3)
        GuidelineRule.objects.update(updated_at=before)
        self.client.post(edit_url(rule), {"title": rule.title, "text": rule.text})
        rule.refresh_from_db()
        self.assertEqual(rule.updated_at, before)

    def test_empty_fields_keep_the_form_open(self):
        rule = self.rule("Be kind")
        response = self.client.post(edit_url(rule), {"title": " ", "text": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["editing"], rule)
        self.assertContains(response, "Add a title.")
        self.assertContains(response, "Say what users should do or avoid.")
        rule.refresh_from_db()
        self.assertEqual(rule.title, "Be kind")

    def test_a_removed_rule_cant_be_edited(self):
        rule = self.rule("Be kind")
        rule.removed_at = timezone.now()
        rule.save()
        response = self.client.post(edit_url(rule), {"title": "x", "text": "y"})
        self.assertEqual(response.status_code, 404)


class AddTests(GuidelinesTestData):
    def test_add_rule_opens_a_form_under_the_last_rule(self):
        response = self.client.get(PAGE, {"add": "1"})
        self.assertTrue(response.context["adding"])
        self.assertContains(response, f'action="{ADD}"')
        self.assertContains(response, 'placeholder="Rule title"')
        self.assertContains(response, 'placeholder="What should users do or avoid?"')
        self.assertContains(response, 'class="guideline-number" aria-hidden="true">6<')
        self.assertNotContains(response, 'href="?add=1"')

    def test_adding_a_rule_puts_it_last(self):
        data = {"title": "Be patient", "text": "Wait for a caregiver to answer."}
        response = self.client.post(ADD, data, follow=True)
        self.assertRedirects(response, f"{PAGE}?done=added")
        self.assertContains(response, "Rule added. Users can now see it.")
        self.assertEqual(self.shown_titles(), [*DEFAULTS, "Be patient"])
        self.assertEqual(self.rule("Be patient").position, 6)

    def test_adding_the_first_rule(self):
        GuidelineRule.objects.all().delete()
        self.client.post(ADD, {"title": "Be kind", "text": "No insults."})
        self.assertEqual(self.rule("Be kind").position, 1)

    def test_add_errors(self):
        response = self.client.post(ADD, {"title": "", "text": "x" * 301})
        self.assertTrue(response.context["adding"])
        self.assertContains(response, "Add a title.")
        self.assertContains(response, "Keep it under 300 characters.")
        self.assertEqual(self.shown_titles(), DEFAULTS)


class RemoveTests(GuidelinesTestData):
    def test_remove_asks_first(self):
        rule = self.rule("Keep personal info private")
        response = self.client.get(PAGE, {"remove": rule.pk})
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Remove this rule?")
        self.assertContains(
            response,
            "Users won’t see “Keep personal info private” in the guidelines anymore.",
        )
        self.assertContains(response, f'action="{remove_url(rule)}"')

    def test_unknown_remove_is_ignored(self):
        response = self.client.get(PAGE, {"remove": "999"})
        self.assertIsNone(response.context["confirm"])

    def test_removing_a_rule(self):
        rule = self.rule("Keep personal info private")
        GuidelineRule.objects.update(updated_at=timezone.now() - timedelta(days=5))
        response = self.client.post(remove_url(rule), follow=True)
        self.assertRedirects(response, f"{PAGE}?done=removed")
        self.assertContains(response, "Rule removed. Users no longer see it.")
        self.assertNotIn("Keep personal info private", self.shown_titles())
        # "Play by the rules" moves up to number 4.
        self.assertContains(response, 'class="guideline-number" aria-hidden="true">4<')
        self.assertNotContains(
            response, 'class="guideline-number" aria-hidden="true">5<'
        )
        # "Last updated" counts the removal.
        rule.refresh_from_db()
        self.assertEqual(guidelines_updated_at(), rule.removed_at)


class ForumPopupTests(GuidelinesTestData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_forum_links_to_the_guidelines(self):
        response = self.client.get(detail_url(self.older))
        self.assertContains(response, f'href="?post={self.older.pk}&amp;guidelines=1"')
        self.assertContains(response, "Community guidelines</a>")
        self.assertNotContains(response, "guidelines-popup")

    def test_popup_shows_the_rules(self):
        self.rule("Be kind").delete()
        response = self.client.get(
            LIST_URL, {"post": self.older.pk, "guidelines": "1", "topic": "questions"}
        )
        self.assertContains(response, 'class="guidelines-popup"')
        self.assertContains(response, "Last updated ")
        self.assertEqual(
            [r.title for r in response.context["guidelines"]], DEFAULTS[1:]
        )
        self.assertContains(response, "Keep it about pets")
        self.assertNotContains(response, "Be kind")
        # Got it goes back to the same post and topic.
        self.assertContains(
            response, f'href="?topic=questions&amp;post={self.older.pk}">Got it'
        )

    def test_popup_without_rules(self):
        GuidelineRule.objects.all().delete()
        response = self.client.get(LIST_URL, {"guidelines": "1"})
        self.assertContains(response, "No guidelines yet.")

    def test_admins_go_to_their_page_instead(self):
        self.client.force_login(self.admin)
        response = self.client.get(LIST_URL, {"guidelines": "1"})
        self.assertContains(response, f'href="{PAGE}"')
        self.assertNotContains(response, "guidelines-popup")
