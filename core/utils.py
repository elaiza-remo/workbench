from django.contrib import messages
from django.shortcuts import redirect, render


def confirm_delete(request, obj, kind, success_url, warning=""):
    """GET shows a confirmation page; POST deletes and redirects."""
    if request.method == "POST":
        label = str(obj)
        obj.delete()
        messages.success(request, f"Deleted {kind} “{label}”.")
        return redirect(success_url)
    return render(request, "core/confirm_delete.html", {
        "obj": obj, "kind": kind, "cancel_url": obj.get_absolute_url(), "warning": warning,
    })
