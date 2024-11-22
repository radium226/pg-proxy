from click import group, version_option


@group()
@version_option("1.0.0")
def app():
    print("Hello, World!")