# Generated by Django 5.1.2 on 2024-10-16 04:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0006_alter_job_employment_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='company_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='job',
            name='requirements',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
