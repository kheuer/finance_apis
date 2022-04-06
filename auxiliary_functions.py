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

def get_api_key(api_name):
    with open("api_keys.yaml") as stream:
        all_keys = yaml.safe_load(stream)
        if api_name in all_keys:
            return all_keys[api_name]
        else:
            raise ValueError(f"There is no saved key available for {api_name}")

