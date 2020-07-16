from asgiref.sync import async_to_sync
from typing import Union

from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db import transaction
from django.db.models.signals import post_save, post_delete, m2m_changed

from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer
from safedelete.signals import post_softdelete

from officehours_api.models import Queue, Meeting, Profile
from officehours_api.permissions import is_host
from officehours_api.serializers import (
    QueueHostSerializer, QueueAttendeeSerializer, UserSerializer
)


class QueueConsumer(JsonWebsocketConsumer):
    _queue_id: int
    _user: User

    @staticmethod
    def get_group_name(queue_id):
        return f'queue_{queue_id}'

    @property
    def queue_id(self):
        return self._queue_id

    @property
    def group_name(self):
        return self.get_group_name(self.queue_id)

    @property
    def user(self):
        return self._user

    def connect(self):
        self._queue_id = int(self.scope['url_route']['kwargs']['queue_id'])
        self._user = self.scope["user"]
        try:
            queue = Queue.objects.get(pk=self.queue_id)
        except Queue.DoesNotExist:
            self.accept()
            self.close(code=4404)
            return

        QueueSerializer = (
            QueueHostSerializer
            if is_host(self.user, queue)
            else QueueAttendeeSerializer
        )

        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        self.accept()
        queue_data = QueueSerializer(queue, context={'user': self.user}).data
        self.send_json({
            'type': 'init',
            'content': queue_data,
        })

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )

    def queue_update(self, event):
        queue = Queue.objects.get(pk=self.queue_id)
        QueueSerializer = (
            QueueHostSerializer
            if is_host(self.user, queue)
            else QueueAttendeeSerializer
        )
        queue_data = QueueSerializer(
            queue,
            context={'user': self.user},
        ).data
        self.send_json({
            'type': 'update',
            'content': queue_data,
        })

    def queue_deleted(self, event):
        self.send_json({
            'type': 'deleted',
        })


def send_queue_update(queue_id: int, channel_layer=None):
    channel_layer = channel_layer or get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        QueueConsumer.get_group_name(queue_id),
        {
            'type': 'queue.update',
        }
    )


def send_queue_delete(queue_id: int, channel_layer=None):
    channel_layer = channel_layer or get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        QueueConsumer.get_group_name(queue_id),
        {
            'type': 'queue.deleted',
        }
    )


@receiver(post_save, sender=Queue)
def trigger_queue_update(sender, instance: Queue, created, **kwargs):
    if instance.deleted:
        return
    transaction.on_commit(lambda: send_queue_update(instance.id))


@receiver(post_softdelete, sender=Queue)
def trigger_queue_delete(sender, instance: Queue, **kwargs):
    transaction.on_commit(lambda: send_queue_delete(instance.id))


@receiver(post_save, sender=Meeting)
@receiver(post_delete, sender=Meeting)
def trigger_queue_update_for_meeting(sender, instance: Meeting, **kwargs):
    if instance.queue_id is None:
        return
    transaction.on_commit(lambda: send_queue_update(instance.queue_id))


@receiver(m2m_changed, sender=Queue.hosts.through)
def trigger_queue_update_for_hosts(sender, instance, action, **kwargs):
    if action == "post_remove" or action == "post_clear" or action == "post_add":
        transaction.on_commit(lambda: send_queue_update(instance.id))


class UsersConsumer(JsonWebsocketConsumer):
    _user: User
    group_name = "users"

    @property
    def user(self):
        return self._user

    def _get_users(self):
        return list(
            UserSerializer(u, context={'user': self.user}).data
            for u in User.objects.all()
        )

    def connect(self):
        self._user = self.scope["user"]
        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        self.accept()
        users_data = self._get_users()
        self.send_json({
            'type': 'init',
            'content': users_data,
        })

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )

    def users_update(self, event):
        # Doesn't scale well - should send only the updated parts instead
        users_data = self._get_users()
        self.send_json({
            'type': 'update',
            'content': users_data,
        })


def send_users_update(channel_layer=None):
    channel_layer = channel_layer or get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        UsersConsumer.group_name,
        {
            'type': 'users.update',
        }
    )


@receiver(post_save, sender=User)
@receiver(post_delete, sender=User)
@receiver(post_save, sender=Profile)
@receiver(post_delete, sender=Profile)
def trigger_users_update(sender, instance: User, created, **kwargs):
    transaction.on_commit(send_users_update)


class UserConsumer(JsonWebsocketConsumer):
    _user_id: int
    _user: User

    @staticmethod
    def get_group_name(user_id):
        return f'user_{user_id}'

    @property
    def user_id(self):
        return self._user_id

    @property
    def group_name(self):
        return self.get_group_name(self.user_id)

    @property
    def user(self):
        return self._user

    def connect(self):
        self._user_id = int(self.scope['url_route']['kwargs']['user_id'])
        self._user = self.scope["user"]
        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        self.accept()
        try:
            user_data = UserSerializer(
                User.objects.get(pk=self.user_id), context={'user': self.user}
            ).data
        except User.DoesNotExist:
            self.close(code=4404)
            return
        self.send_json({
            'type': 'init',
            'content': user_data,
        })

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )

    def user_update(self, event):
        user_data = UserSerializer(
            User.objects.get(pk=self.user_id), context={'user': self.user}
        ).data
        self.send_json({
            'type': 'update',
            'content': user_data,
        })

    def user_deleted(self, event):
        self.send_json({
            'type': 'deleted',
        })


def send_user_update(user_id: int, channel_layer=None):
    channel_layer = channel_layer or get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        UserConsumer.get_group_name(user_id),
        {
            'type': 'user.update',
        }
    )


def send_user_deleted(user_id: int, channel_layer=None):
    channel_layer = channel_layer or get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        UserConsumer.get_group_name(user_id),
        {
            'type': 'user.deleted',
        }
    )


@receiver(post_save, sender=User)
def trigger_user_update(sender, instance: User, **kwargs):
    transaction.on_commit(lambda: send_user_update(instance.id))


@receiver(post_delete, sender=User)
def trigger_user_deleted(sender, instance: User, **kwargs):
    transaction.on_commit(lambda: send_user_deleted(instance.id))


@receiver(post_save, sender=Profile)
@receiver(post_delete, sender=Profile)
def trigger_user_update_for_profile(sender, instance: Profile, **kwargs):
    transaction.on_commit(lambda: send_user_update(instance.user.id))


@receiver(m2m_changed, sender=User.meeting_set.through)
def trigger_user_update_for_meetings(
    sender, instance: Union[User, Meeting],
    action, reverse, model, pk_set, **kwargs
):
    if not (
        action == "post_remove"
        or action == "post_clear"
        or action == "post_add"
    ):
        return
    if isinstance(instance, User):
        transaction.on_commit(lambda: send_user_update(instance.id))
    else:  # is Meeting
        for user_id in pk_set:
            transaction.on_commit(lambda: send_user_update(user_id))
