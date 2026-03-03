def normalize_decimal_input(value):
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if not normalized:
        return normalized

    normalized = normalized.replace("R$", "").replace(" ", "")
    comma_index = normalized.rfind(",")
    dot_index = normalized.rfind(".")

    if comma_index != -1 and dot_index != -1:
        if comma_index > dot_index:
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif comma_index != -1:
        normalized = normalized.replace(",", ".")

    return normalized
