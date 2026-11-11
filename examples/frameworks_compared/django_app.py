"""Ті самі нотатки на «голому» Django: URLConf + view + Form, без DRF. Один файл заради порівняння."""
import json

from django import forms
from django.conf import settings

settings.configure(ROOT_URLCONF=__name__, ALLOWED_HOSTS=["*"], SECRET_KEY="demo-only")

from django.http import JsonResponse                      # noqa: E402 — після settings.configure
from django.urls import path                              # noqa: E402
from django.views.decorators.csrf import csrf_exempt      # noqa: E402
from django.views.decorators.http import require_http_methods  # noqa: E402

NOTES: list[dict] = []


class NoteForm(forms.Form):
    title = forms.CharField(min_length=1, max_length=200)
    priority = forms.IntegerField(min_value=1, max_value=4, required=False)


class LimitForm(forms.Form):
    limit = forms.IntegerField(min_value=1, max_value=100, required=False)


@csrf_exempt                       # API без cookie-сесії; у справжньому проєкті — DRF або Ninja
@require_http_methods(["GET", "POST"])
def notes(request):
    if request.method == "GET":
        form = LimitForm(request.GET)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        return JsonResponse(NOTES[: form.cleaned_data["limit"] or 10], safe=False)
    form = NoteForm(json.loads(request.body or b"{}"))
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    note = {"id": len(NOTES) + 1, "title": form.cleaned_data["title"],
            "priority": form.cleaned_data["priority"] or 1}
    NOTES.append(note)
    return JsonResponse(note, status=201)


urlpatterns = [path("api/notes", notes)]          # маршрути — таблицею URLConf, а не декораторами
