"""
Custom Social Auth pipeline steps for VATSIM Connect.
"""

from django.contrib.auth import get_user_model

User = get_user_model()


def get_or_create_user(backend, details, uid, user=None, *args, **kwargs):
    """
    Look up the User by CID; create one if first login.
    Replaces the default social-auth create_user pipeline step.
    """
    if user:
        return {"user": user}

    cid = details.get("cid")
    if not cid:
        return None

    try:
        existing = User.objects.get(cid=int(cid))
        return {"user": existing, "is_new": False}
    except User.DoesNotExist:
        pass

    new_user = User.objects.create(
        username=str(cid),
        cid=int(cid),
        email=details.get("email", ""),
        vatsim_name=details.get("vatsim_name", ""),
        rating=details.get("rating", 1),
    )
    new_user.set_unusable_password()
    new_user.save()
    return {"user": new_user, "is_new": True}


def update_user_details(backend, details, user=None, is_new=False, *args, **kwargs):
    """Keep name, email, and rating in sync with VATSIM on every login."""
    if user is None:
        return

    changed = False
    vatsim_name = details.get("vatsim_name", "")
    email = details.get("email", "")
    rating = details.get("rating")

    if vatsim_name and user.vatsim_name != vatsim_name:
        user.vatsim_name = vatsim_name
        changed = True
    if email and user.email != email:
        user.email = email
        changed = True
    if rating and user.rating != rating:
        user.rating = rating
        changed = True

    if changed:
        user.save(update_fields=["vatsim_name", "email", "rating"])
