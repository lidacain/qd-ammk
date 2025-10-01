from django.db import models
from django.contrib.auth import get_user_model


User = get_user_model()


class UserActivityLog(models.Model):
    MAX_URL_DISPLAY_LENGTH = 60

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField()
    url = models.URLField(max_length=1000)
    role = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        if len(self.url) > self.MAX_URL_DISPLAY_LENGTH:
            short_url = self.url[:self.MAX_URL_DISPLAY_LENGTH - 3] + '...'
        else:
            short_url = self.url
        return f"{self.user} | {self.ip_address} | {short_url} | {self.timestamp}"