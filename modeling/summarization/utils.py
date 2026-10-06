def extend_string_range(input_string):
    if input_string is None:
        return []

    result = []
    for part in input_string.split(','):
        if '-' in part:
            a, b = part.split('-')
            a, b = int(a), int(b)
            result.extend(range(a, b + 1))
        else:
            a = int(part)
            result.append(a)
    return result

