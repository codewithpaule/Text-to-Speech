from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = 'Seed default subscription plans'

    def handle(self, *args, **options):
        plans = [
            {'name': 'Basic', 'price': 9.99, 'duration_days': 30, 'description': 'Great for starters'},
            {'name': 'Pro', 'price': 19.99, 'duration_days': 30, 'description': 'For professionals'},
            {'name': 'Business', 'price': 49.99, 'duration_days': 30, 'description': 'For teams and businesses'},
        ]
        for p in plans:
            Plan.objects.update_or_create(name=p['name'], defaults=p)
        self.stdout.write(self.style.SUCCESS('Plans seeded'))