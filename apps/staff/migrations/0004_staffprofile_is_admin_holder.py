from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("staff", "0003_alter_staffprofile_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="is_admin_holder",
            field=models.BooleanField(default=False),
        ),
    ]
