import json
import subprocess
import hashlib
import os.path
import shlex
import gevent
from django.db import models
from django_mysql.models import JSONField, Model
from django.core.mail import send_mail
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.base_user import BaseUserManager
from django.conf import settings


# contains helper methods for the User model
class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Please provide an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('The field is_superuser should be set to True.')

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Meta:
        db_table = "users"

    email = models.EmailField(max_length=255, unique=True)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    is_active = models.BooleanField(db_column='isActive', default=True)
    full_name = models.CharField(db_column='fullName', max_length=255, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def get_full_name(self):
        if self.full_name is not None:
            return self.full_name
        else:
            return self.name

    def get_short_name(self):
        return self.name

    def email_user(self, subject, message, from_email=None, **kwargs):
        send_mail(subject, message, from_email, [self.email], **kwargs)


class PasswordReset(Model):
    class Meta:
        db_table = "password_resets"

    email = models.CharField(max_length=255)
    token = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class Chart(Model):
    class Meta:
        db_table = "charts"

    id = models.AutoField(primary_key=True)
    config = JSONField()
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    last_edited_by = models.ForeignKey(User, db_column='lastEditedByUserId', to_field='name', on_delete=models.DO_NOTHING, blank=True, null=True)
    last_edited_at = models.DateTimeField(db_column='lastEditedAt')
    starred = models.BooleanField(default=False)
    published_at = models.DateTimeField(db_column='publishedAt', null=True)
    published_by = models.ForeignKey(User, db_column="publishedByUserId", to_field='name', on_delete=models.DO_NOTHING, blank=True, null=True, related_name="published_charts")

    @classmethod
    def bake(cls, user, slug):
        email = shlex.quote(user.email)
        name = shlex.quote(user.get_full_name())
        slug = shlex.quote(slug)
        cmd = f"node {settings.BASE_DIR}/dist/src/bakeCharts.js {email} {name} {slug} >> /tmp/{settings.DB_NAME}-static.log 2>&1"

        print(cmd)
        subprocess.Popen(cmd, shell=True)

    @classmethod
    def owid_commit(cls):
        """
        :return: Will return latest commit revision for the repo
        """
        git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], shell=False)
        return str(git_commit)

    def show_type(self):
        type = "Unknown"
        config = self.config

        if config['type'] == "LineChart":
            type = "Line Chart"
        elif config['type'] == "ScatterPlot":
            type = "Scatter Plot"
        elif config['type'] == "StackedArea":
            type = "Stacked Area"
        elif config['type'] == "MultiBar":
            type = "Multi Bar"
        elif config['type'] == "HorizontalMultiBar":
            type = "Horizontal Multi Bar"
        elif config['type'] == "DiscreteBar":
            type = "Discrete Bar"
        elif config['type'] == "SlopeChart":
            type = "Slope Chart"

        if config.get("tab") == "map":
            if config.get("hasChartTab"):
                return "Map + " + type
            else:
                return "Map"
        else:
            if config.get("hasMapTab"):
                return type + " + Map"
            else:
                return type


# OBSOLETE
class DatasetCategory(Model):
    class Meta:
        db_table = "dataset_categories"

    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    fetcher_autocreated = models.BooleanField(default=False)


# OBSOLETE
class DatasetSubcategory(Model):
    class Meta:
        db_table = "dataset_subcategories"
        unique_together = (('name', 'categoryId'),)

    name = models.CharField(max_length=255)
    categoryId = models.ForeignKey(DatasetCategory, blank=True, null=True, on_delete=models.DO_NOTHING,
                                      db_column='categoryId')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Tag(Model):
    class Meta:
        db_table = "tags"

    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    parent_id = models.ForeignKey('self', db_column='parentId', blank=True, null=True)
    is_bulk_import = models.BooleanField(db_column='isBulkImport', default=False) # used to be fetcher_autocreated
    special_type = models.CharField(db_column='specialType', max_length=255)


class Dataset(Model):
    class Meta:
        db_table = "datasets"
        unique_together = (('name', 'namespace'),)

    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    namespace = models.CharField(max_length=255, default='owid')
    is_private = models.BooleanField(db_column='isPrivate', default=False)
    created_by = models.ForeignKey(User, to_field='name', on_delete=models.DO_NOTHING,
                                    db_column='createdByUserId', blank=True, null=True)
    metadata_edited_at = models.DateTimeField(db_column='metadataEditedAt', auto_now_add=True)
    metadata_edited_by = models.ForeignKey(User, to_field='name', on_delete=models.DO_NOTHING,
                                    db_column='metadataEditedByUserId', blank=True, null=True)
    data_edited_at = models.DateTimeField(db_column='dataEditedAt', auto_now_add=True)
    data_edited_by = models.ForeignKey(User, to_field='name', on_delete=models.DO_NOTHING,
                                    db_column='dataEditedByUserId', blank=True, null=True)


class DatasetTag(Model):
    class Meta:
        db_table = "dataset_tags"

    dataset_id = models.ForeignKey(Dataset, db_column='datasetId', blank=False, null=False, primary_key=True)
    tag_id = models.ForeignKey(Tag, db_column='tagId', blank=False, null=False)


class Source(Model):
    class Meta:
        db_table = 'sources'
        unique_together = (('name', 'datasetId'),)

    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    datasetId = models.ForeignKey(Dataset, db_column='datasetId', blank=True, null=True)


# OBSOLETE
class VariableType(Model):
    class Meta:
        db_table = 'variable_types'

    name = models.CharField(max_length=255)
    isSortable = models.BooleanField(db_column='isSortable', default=False)


class Variable(Model):
    class Meta:
        db_table = 'variables'
        unique_together = (('code', 'datasetId'), ('name', 'datasetId'),)

    name = models.CharField(max_length=1000)
    unit = models.CharField(max_length=255)
    short_unit = models.CharField(db_column='shortUnit', max_length=255, null=True)

    display = JSONField()

    description = models.TextField(blank=True, null=True)
    datasetId = models.ForeignKey(Dataset, on_delete=models.CASCADE, db_column='datasetId')
    sourceId = models.ForeignKey(Source, on_delete=models.DO_NOTHING, db_column='sourceId')
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    # variableTypeId = models.ForeignKey(VariableType, on_delete=models.DO_NOTHING, db_column='variableTypeId')
    # uploaded_by = models.ForeignKey(User, to_field='name', on_delete=models.DO_NOTHING, db_column='uploaded_by',
    #                                 blank=True, null=True)
    # uploaded_at = models.DateTimeField(db_column='uploadedAt', auto_now_add=True)
    code = models.CharField(max_length=255, blank=True, null=True)
    coverage = models.CharField(max_length=255)
    timespan = models.CharField(max_length=255)


class ChartDimension(Model):
    class Meta:
        db_table = "chart_dimensions"

    chartId = models.ForeignKey(Chart, on_delete=models.CASCADE, db_column='chartId')
    variableId = models.ForeignKey(Variable, models.DO_NOTHING, db_column='variableId')
    order = models.IntegerField()
    property = models.CharField(max_length=255)

class ChartSlugRedirect(Model):
    class Meta:
        db_table = 'chart_slug_redirects'

    slug = models.CharField(unique=True, max_length=255)
    chart_id = models.IntegerField()


class Entity(Model):
    class Meta:
        db_table = "entities"

    code = models.CharField(max_length=255, blank=True, null=True, unique=True)
    name = models.CharField(max_length=255, unique=True)
    validated = models.BooleanField()
    created_at = models.DateTimeField(db_column='createdAt', auto_now_add=True)
    updated_at = models.DateTimeField(db_column='updatedAt', auto_now=True)
    displayName = models.CharField(db_column='displayName', max_length=255)


class DataValue(Model):
    class Meta:
        db_table = "data_values"
        unique_together = (('entityId', 'variableId', 'year'),)

    value = models.CharField(max_length=255)
    entityId = models.ForeignKey(Entity, on_delete=models.DO_NOTHING, db_column='entityId')
    variableId = models.ForeignKey(Variable, on_delete=models.CASCADE, db_column='variableId')
    year = models.IntegerField()


class License(Model):
    class Meta:
        db_table = 'licenses'

    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Logo(Model):
    class Meta:
        db_table = 'logos'

    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    svg = models.TextField()


class Setting(Model):
    class Meta:
        db_table = 'settings'

    meta_name = models.CharField(max_length=255)
    meta_value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserInvitation(Model):
    class Meta:
        db_table = 'user_invitations'

    code = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    user_id = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='user_id')
    status = models.CharField(max_length=10, choices=(('pending', 'pending'), ('successful', 'successful'),
                                                      ('canceled', 'canceled'), ('expired', 'expired')))
    valid_till = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
