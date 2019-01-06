#
# Credit to http://www.emptypage.jp/notes/pyevent.en.html for initial implementation.
#

class Event(object):

    pass_sender_obj = 1

    def __init__(self, doc=None, fire_type=pass_sender_obj):
        """
        :param doc: Documentation
        :param fire_type: 0: Pass sender object, 1: Do not.
        """
        self.__doc__    = doc
        self.fire_type  = fire_type

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return EventHandler(self, obj)

    def __set__(self, obj, value):
        pass


class EventHandler(object):

    def __init__(self, event, obj):

        self.event = event
        self.obj = obj

    def _getfunctionlist(self):

        """(internal use) """

        try:
            eventhandler = self.obj.__eventhandler__
        except AttributeError:
            eventhandler = self.obj.__eventhandler__ = {}
        return eventhandler.setdefault(self.event, [])

    def add(self, func):

        """Add new event handler function.

        Event handler function must be defined like func(sender, earg).
        You can add handler also by using '+=' operator.
        """

        self._getfunctionlist().append(func)
        return self

    def remove(self, func):

        """Remove existing event handler function.

        You can remove handler also by using '-=' operator.
        """

        self._getfunctionlist().remove(func)
        return self

    def fire(self, **kwargs):

        """Fire event and call all handler functions

        You can call EventHandler object itself like e(earg) instead of
        e.fire(earg).
        """

        # Keep track of event count
        try:
            event_counter = self.obj.__eventcounter__
        except AttributeError:
            event_counter = self.obj.__eventcounter__ = {}
        if self.event in event_counter:
            event_counter[self.event] += 1
        else:
            event_counter[self.event]  = 1

        for func in self._getfunctionlist():
            if self.event.fire_type == self.event.pass_sender_obj:
                func(self.obj, **kwargs)
            else:
                func(**kwargs)

    __iadd__ = add
    __isub__ = remove
    __call__ = fire