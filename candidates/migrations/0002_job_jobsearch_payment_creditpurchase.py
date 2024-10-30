# Generated by Django 5.1.2 on 2024-10-09 03:22

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('requirements', models.TextField(blank=True, null=True)),
                ('company_name', models.CharField(max_length=255)),
                ('company_size', models.IntegerField(blank=True, null=True)),
                ('location', models.CharField(blank=True, max_length=255, null=True)),
                ('employment_type', models.CharField(choices=[('remote', 'Remote'), ('hybrid', 'Hybrid'), ('on-site', 'On-site')], default='on-site', max_length=50)),
                ('linkedin_profiles', models.JSONField(blank=True, null=True)),
                ('original_url', models.URLField()),
                ('salary_range', models.CharField(blank=True, max_length=100, null=True)),
                ('benefits', models.JSONField(blank=True, null=True)),
                ('skills_required', models.JSONField(blank=True, null=True)),
                ('posted_date', models.DateField(blank=True, null=True)),
                ('expiration_date', models.DateField(blank=True, null=True)),
                ('industry', models.CharField(blank=True, max_length=100, null=True)),
                ('job_type', models.CharField(choices=[('full-time', 'Full-time'), ('part-time', 'Part-time'), ('contract', 'Contract'), ('freelance', 'Freelance'), ('CDD', 'CDD (Fixed-term)'), ('CDI', 'CDI (Indefinite-term)'), ('other', 'Other')], default='full-time', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='JobSearch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('similarity_score', models.FloatField()),
                ('search_date', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('matched', 'Matched'), ('applied', 'Applied')], default='matched', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.candidate')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.job')),
            ],
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='USD', max_length=10)),
                ('payment_method', models.CharField(choices=[('paypal', 'PayPal'), ('stripe', 'Stripe')], default='stripe', max_length=50)),
                ('transaction_id', models.CharField(max_length=255, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='pending', max_length=50)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.candidate')),
            ],
        ),
        migrations.CreateModel(
            name='CreditPurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('credits_purchased', models.IntegerField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.candidate')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.payment')),
            ],
        ),
    ]