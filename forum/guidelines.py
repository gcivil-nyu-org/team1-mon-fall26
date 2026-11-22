"""#105 Manage Community Guidelines, laid out as in Kat's Figma: admins open
"Community guidelines" from the Forum in Explore and see the numbered rules.

- Edit (pencil) turns a rule into a small form in place, with Cancel and Save
  ("Edit Community Guidelines"); Save stays gray until something changes.
- Add rule opens the same form under the last rule ("Add Community
  Guidelines").
- Remove (trash) asks first in a popup ("Remove Community Guidelines").

After each change a green banner says so ("... Confirmation" frames). Everyone
else reads the rules in a popup on the Forum ("Community Guidelines (User)")."""

from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from staff.views import staff_required

from .forms import GuidelineRuleForm
from .models import GuidelineRule, guidelines_updated_at

# The banner after a change (?done=), with the Figma's wording.
DONE = {
    "saved": "Rule saved. Users can now see the update.",
    "added": "Rule added. Users can now see it.",
    "removed": "Rule removed. Users no longer see it.",
}


def _page_url(**params):
    url = reverse("forum:guidelines")
    if params:
        url += "?" + "&".join(f"{key}={value}" for key, value in params.items())
    return url


def _rule(pk):
    return get_object_or_404(GuidelineRule.objects.shown(), pk=pk)


def _page(request, editing=None, form=None, adding=False):
    rules = list(GuidelineRule.objects.shown())
    if editing is None and not adding:
        wanted = request.GET.get("edit", "")
        if wanted.isdigit():
            editing = next((r for r in rules if r.pk == int(wanted)), None)
        adding = editing is None and request.GET.get("add") == "1"
    if form is None and editing is not None:
        form = GuidelineRuleForm(instance=editing)
    if form is None and adding:
        form = GuidelineRuleForm()

    confirm = None
    wanted = request.GET.get("remove", "")
    if wanted.isdigit() and form is None:
        confirm = next((r for r in rules if r.pk == int(wanted)), None)

    return render(
        request,
        "forum/guidelines.html",
        {
            "rules": rules,
            "editing": editing,
            "adding": adding,
            "form": form,
            "confirm": confirm,
            "updated_at": guidelines_updated_at(),
            "done": DONE.get(request.GET.get("done")),
        },
    )


@staff_required
def guidelines(request):
    """The admin page with every rule."""
    return _page(request)


@require_POST
@staff_required
def add_rule(request):
    form = GuidelineRuleForm(request.POST)
    if not form.is_valid():
        return _page(request, form=form, adding=True)
    rule = form.save(commit=False)
    last = GuidelineRule.objects.shown().aggregate(last=Max("position"))["last"]
    rule.position = (last or 0) + 1
    rule.save()
    return redirect(_page_url(done="added"))


@require_POST
@staff_required
def edit_rule(request, pk):
    rule = _rule(pk)
    form = GuidelineRuleForm(request.POST, instance=rule)
    if not form.is_valid():
        return _page(request, editing=rule, form=form)
    if form.has_changed():
        form.save()
    return redirect(_page_url(done="saved"))


@require_POST
@staff_required
def remove_rule(request, pk):
    rule = _rule(pk)
    rule.removed_at = timezone.now()
    rule.save(update_fields=["removed_at"])
    return redirect(_page_url(done="removed"))
