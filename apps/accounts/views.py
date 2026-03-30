from django.contrib.auth import logout
from django.shortcuts import redirect, render
from .models import NameDisplay


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return render(request, "accounts/login.html")


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("public:homepage")


def settings_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    if request.method == "POST":
        display = request.POST.get("name_display")
        if display in NameDisplay.values:
            request.user.name_display = display
            request.user.save(update_fields=["name_display"])
        return redirect("accounts:settings")

    return render(request, "accounts/settings.html", {"NameDisplay": NameDisplay})
