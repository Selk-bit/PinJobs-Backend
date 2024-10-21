# Generated by Django 5.1.2 on 2024-10-15 07:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0004_alter_cvdata_cv'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='is_scraping',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='candidate',
            name='last_scrape_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='candidate',
            name='num_jobs_to_scrape',
            field=models.IntegerField(default=10),
        ),
        migrations.AddField(
            model_name='candidate',
            name='scrape_interval',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='candidate',
            name='scrape_unit',
            field=models.CharField(choices=[('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks')], default='hours', max_length=10),
        ),
    ]
