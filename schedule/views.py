# schedule/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.views.decorators.http import require_http_methods
from .models import ScheduleTemplate

def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return None

@require_http_methods(["GET", "POST"])
def templates_list_create(request, group):
    # GET: lista schematów w danym dziale (współdzielona)
    if request.method == "GET":
        qs = ScheduleTemplate.objects.filter(group=group).order_by("name")
        items = [
            {
                "name": t.name,
                "positions": t.positions,
                "group": t.group,
                "updated_at": t.updated_at.isoformat(),
                "created_at": t.created_at.isoformat(),
            } for t in qs
        ]
        return JsonResponse({"items": items})

    # POST: upsert (group + name)
    payload = _parse_json(request)
    if payload is None:
        return HttpResponseBadRequest("Invalid JSON")

    name = (payload.get("name") or "").strip()
    positions = payload.get("positions")
    if not name:
        return HttpResponseBadRequest("Field 'name' is required")
    if not isinstance(positions, list) or not all(isinstance(p, str) and p.strip() for p in positions):
        return HttpResponseBadRequest("Field 'positions' must be a non-empty list of strings")

    obj, _created = ScheduleTemplate.objects.update_or_create(
        group=group, name=name,
        defaults={"positions": positions}
    )
    return JsonResponse({"ok": True, "name": obj.name, "group": obj.group, "updated_at": obj.updated_at.isoformat()})

@require_http_methods(["GET", "PUT", "DELETE"])
def templates_retrieve_update_delete(request, group, name):
    try:
        obj = ScheduleTemplate.objects.get(group=group, name=name)
    except ScheduleTemplate.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "name": obj.name,
            "positions": obj.positions,
            "group": obj.group,
            "updated_at": obj.updated_at.isoformat(),
            "created_at": obj.created_at.isoformat(),
        })

    if request.method == "PUT":
        payload = _parse_json(request)
        if payload is None:
            return HttpResponseBadRequest("Invalid JSON")

        new_name = (payload.get("name") or obj.name).strip()
        positions = payload.get("positions", obj.positions)

        if not isinstance(positions, list) or not all(isinstance(p, str) and p.strip() for p in positions):
            return HttpResponseBadRequest("Field 'positions' must be a non-empty list of strings")

        if new_name != obj.name and ScheduleTemplate.objects.filter(group=group, name=new_name).exists():
            return HttpResponseBadRequest("Template with this name already exists")

        obj.name = new_name
        obj.positions = positions
        obj.save()
        return JsonResponse({"ok": True})

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    return HttpResponseNotAllowed(["GET", "PUT", "DELETE"])
