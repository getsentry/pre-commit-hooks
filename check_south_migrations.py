#!/usr/bin/env python
from __future__ import print_function, absolute_import

import argparse
import os
import six
import sys
import unittest


def import_django(django_conf=None):
    if django_conf is not None:
        os.environ['DJANGO_SETTINGS_MODULE'] = django_conf

    os.environ['_SENTRY_SKIP_CONFIGURATION'] = '1'
    os.environ['SOUTH_TESTS_MIGRATE'] = '1'

    import sentry.utils.pytest.sentry as sentry_test
    sentry_test.register_extensions = lambda: None

    # Most of these imports can be mocked as noop, but I don't know yet how to do it properly :(
    #
    # from sentry.runner.initializer import (
    #     bootstrap_options, configure_structlog, initialize_receivers, fix_south,
    #     bind_cache_to_option_store, setup_services
    # )

    sentry_test.pytest_configure({})


def check_missing_migrations(app, django_conf=None):
    """
    Check that the code and the migrations are in sync for the given app.
    Based on the code from "south/management/commands/schemamigration.py"
    """
    import_django(django_conf)

    from django.db import models
    from south.migration import Migrations
    from south.creator import changes, actions, freezer

    assert models.get_app(
        app), "There is no enabled application matching '%s'." % app

    # Get the Migrations for this app (creating the migrations dir if needed)
    migrations = Migrations(app, force_creation=False, verbose_creation=True)

    # Get the latest migration
    last_migration = migrations[-1]

    # Construct two model dicts to run the differ on.
    old_defs = dict(
        (k, v) for k, v in last_migration.migration_class().models.items()
        if k.split(".")[0] == migrations.app_label()
    )
    assert old_defs

    new_defs = dict(
        (k, v) for k, v in freezer.freeze_apps([migrations.app_label()]).items()
        if k.split(".")[0] == migrations.app_label()
    )
    assert new_defs

    change_source = changes.AutoChanges(
        migrations=migrations,
        old_defs=old_defs,
        old_orm=last_migration.orm(),
        new_defs=new_defs,
    )

    # Get the actions, and then insert them into the actions lists
    forwards_actions = []
    for action_name, params in change_source.get_changes():
        # Run the correct Action class
        try:
            action_class = getattr(actions, action_name)
        except AttributeError:
            raise ValueError(
                "Invalid action name from source: %s" % action_name)
        else:
            action = action_class(**params)
            forwards_actions.append(action)
            print(action.console_line(), file=sys.stderr)   # noqa: B314
            print(action.forwards_code(), file=sys.stderr)  # noqa: B314
            print('', file=sys.stderr)                      # noqa: B314

    if forwards_actions != []:
        print('\n'.join([
            'Ungenerated/unmerged migrations found.',
            'You can run "sentry django schemamigration sentry --auto" to generate the missing migrations.',
        ]))
        confirm = raw_input('Are you sure you want to continue? [y/N] ')
        if confirm.lower() not in ['y', 'yes']:
            print('Aborting.')
            return False

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*')
    parser.add_argument('--app', action='append', dest='apps',
                        type=str, required=True)
    parser.add_argument('--conf', dest='django_conf',
                        type=str)
    args = parser.parse_args()

    rc = 0
    for app in args.apps:
        if not check_missing_migrations(app, args.django_conf):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
