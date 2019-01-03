from typing import List, Iterable

from pybel.manager.models import Network
from pybel_web.manager import WebManager, iter_recent_public_networks, iter_unique_networks
from pybel_web.models import User
from tests.cases import TemporaryCacheMethodMixin
from flask_security import SQLAlchemyUserDatastore

def get_networks_with_permission(manager: WebManager, user: User) -> List[Network]:
    """Get all networks tagged as public or uploaded by the current user.

    :return: A list of all networks tagged as public or uploaded by the current user
    """
    if not user.is_authenticated:
        return list(iter_recent_public_networks(manager))

    if user.is_admin:
        return manager.list_recent_networks()

    return list(iter_unique_networks(manager.iter_networks_with_permission(user)))



def iterate_networks_for_user(manager: WebManager,
                              user_datastore: SQLAlchemyUserDatastore,
                              user: User) -> Iterable[Network]:
    """Iterate over a user's networks."""
    yield from iter_recent_public_networks(manager)
    yield from user.iter_available_networks()

    # TODO reinvestigate how "organizations" are handled
    if user.is_scai:
        role = user_datastore.find_or_create_role(name='scai')
        for user in role.users:
            yield from user.iter_owned_networks()


class TestGetNetworks(TemporaryCacheMethodMixin):
    """"""

    def populate(self):
        """Set up the cache with some users, networks, and projects."""
