from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_alter_event_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="event_type",
            field=models.CharField(
                choices=[("regular", "Regular"), ("periodical", "Periodical")],
                db_index=True,
                default="periodical",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="end_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
