from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Global identity. A user reaches tenant data only through an active
    TenantMembership; platform admins hold is_platform_admin and never a
    tenant-bound token by default.
    """

    is_platform_admin = models.BooleanField(default=False)
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="user_set",
        related_query_name="user",
        db_table="accounts_user_groups_tixelise",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_set",
        related_query_name="user",
        db_table="accounts_user_user_permissions_tixelise",
    )

    class Meta(AbstractUser.Meta):
        db_table = "accounts_user_tixelise"

    def save(self, *args, **kwargs):
        # Every Django superuser is automatically a platform admin —
        # covers createsuperuser, create_superuser(), and admin edits.
        if self.is_superuser:
            self.is_platform_admin = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
