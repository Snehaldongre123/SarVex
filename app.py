from flask import Flask

# Create a Flask application instance
app = Flask(__name__)

# Define a route for the home page ('/')
@app.route('/')
def hello_world():
    """Returns a simple 'Hello World' message for the home page."""
    return 'Hello World'

# Run the application if the script is executed directly
if __name__ == '__main__':
    # Bind to PORT if defined as an environment variable, otherwise default to 5000.
    # The host '0.0.0.0' makes the server externally visible (useful for Docker/deployment).
    app.run(host='0.0.0.0', port=5000)
