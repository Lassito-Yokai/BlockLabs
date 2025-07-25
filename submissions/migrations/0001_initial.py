# Generated by Django 4.2.7 on 2025-07-22 11:01

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Submission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Nom de la soumission')),
                ('region', models.CharField(choices=[('EMA', 'Union Européenne (EMA)'), ('FDA', 'États-Unis (FDA)'), ('HC', 'Canada (Health Canada)'), ('PMDA', 'Japon (PMDA)')], max_length=10, verbose_name='Pays/Région')),
                ('variation_type', models.CharField(choices=[('IA', 'Variation Type IA'), ('IB', 'Variation Type IB'), ('II', 'Variation Type II'), ('MAA', 'Marketing Authorization Application')], max_length=10, verbose_name='Type de variation')),
                ('change_description', models.TextField(verbose_name='Description du changement')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('in_progress', 'En cours'), ('submitted', 'Soumis'), ('approved', 'Approuvé')], default='draft', max_length=20, verbose_name='Statut')),
                ('progress', models.IntegerField(default=0, verbose_name='Progression (%)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Soumission',
                'verbose_name_plural': 'Soumissions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SubmissionSuggestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('suggestion_type', models.CharField(choices=[('structure', 'Structure CTD optimisée'), ('missing_section', 'Sections manquantes détectées'), ('recommendation', 'Recommandation')], max_length=50)),
                ('is_applied', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('submission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suggestions', to='submissions.submission')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SubmissionModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_type', models.CharField(choices=[('M1', 'Module 1 - Administrative Information'), ('M2', 'Module 2 - Summaries'), ('M3', 'Module 3 - Quality'), ('M4', 'Module 4 - Nonclinical Study Reports'), ('M5', 'Module 5 - Clinical Study Reports')], max_length=2)),
                ('title', models.CharField(max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('order', models.IntegerField(default=0)),
                ('submission', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='modules', to='submissions.submission')),
            ],
            options={
                'ordering': ['order'],
                'unique_together': {('submission', 'module_type')},
            },
        ),
        migrations.CreateModel(
            name='ModuleSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section_number', models.CharField(max_length=10, verbose_name='Numéro de section')),
                ('title', models.CharField(max_length=200, verbose_name='Titre')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('template_content', models.TextField(blank=True, verbose_name='Contenu du template')),
                ('is_completed', models.BooleanField(default=False, verbose_name='Complété')),
                ('order', models.IntegerField(default=0)),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='submissions.submissionmodule')),
            ],
            options={
                'ordering': ['order'],
                'unique_together': {('module', 'section_number')},
            },
        ),
        migrations.CreateModel(
            name='FormattedTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_name', models.CharField(max_length=200)),
                ('version', models.CharField(default='Version 5', max_length=50)),
                ('division', models.CharField(default='Information Management Division', max_length=200)),
                ('date_created', models.DateField(auto_now_add=True)),
                ('applicant_name', models.CharField(blank=True, max_length=200, verbose_name='Applicant/MAH Name')),
                ('customer_account_number', models.CharField(blank=True, max_length=100, verbose_name='Customer Account Number')),
                ('customer_reference', models.CharField(blank=True, max_length=100, verbose_name='Customer Reference / Purchase Order Number')),
                ('inn_code', models.CharField(blank=True, max_length=100, verbose_name='INN / Active substance/ATC Code')),
                ('product_name', models.CharField(blank=True, max_length=200, verbose_name='Product Name of centrally authorised medicinal product(s)')),
                ('nationally_authorised', models.BooleanField(default=False, verbose_name='Nationally Authorised Product(s)')),
                ('product_procedure_number', models.CharField(blank=True, max_length=100)),
                ('national_marketing_auth_no', models.BooleanField(default=False)),
                ('new_procedure', models.BooleanField(default=False, verbose_name='A submission of a new procedure')),
                ('response_supplementary', models.BooleanField(default=False, verbose_name='A response/supplementary information to an on-going procedure')),
                ('unit_type', models.CharField(blank=True, max_length=100, verbose_name='Unit Type')),
                ('mode_single', models.BooleanField(default=True, verbose_name='Single')),
                ('mode_grouping', models.BooleanField(default=False, verbose_name='Grouping')),
                ('procedure_type', models.CharField(default='MAA - Marketing Authorisation Application', max_length=200)),
                ('description_submission', models.TextField(blank=True, verbose_name='Description of submission')),
                ('related_products', models.TextField(blank=True, verbose_name='Centrally authorised medicinal products for which the same change(s) are being applied')),
                ('rmp_included', models.BooleanField(default=False, verbose_name='RMP included in this submission')),
                ('rmp_version', models.CharField(blank=True, max_length=50, verbose_name='RMP version')),
                ('related_submission_numbers', models.CharField(blank=True, max_length=200, verbose_name='Related submission numbers')),
                ('ectd_sequence', models.CharField(blank=True, max_length=100, verbose_name='eCTD sequence')),
                ('contact_content', models.TextField(blank=True, verbose_name="Contact Persons' details (include email address) - Content")),
                ('contact_technical', models.TextField(blank=True, verbose_name="Contact Persons' details - eCTD technical questions")),
                ('section', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='formatted_template', to='submissions.modulesection')),
            ],
        ),
    ]
