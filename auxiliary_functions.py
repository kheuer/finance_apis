import yaml

def is_number(val):
    if isinstance(val, bool):
        return False
    else:
        try:
            int(val)
            return True
        except ValueError:
            return False
        except TypeError:
            return False

