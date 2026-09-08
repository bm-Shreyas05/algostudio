class ValidationError(Exception):
    pass

def validate(n):
    if n < 0:
        raise ValidationError("negative not allowed")
    return n

for v in [3, -1]:
    try:
        print(validate(v))
    except ValidationError as exc:
        print("error:", exc)
