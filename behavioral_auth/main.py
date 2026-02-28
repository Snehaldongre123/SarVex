# main.py

def main():
    """
    The main function of the script.
    """
    print("Hello, world! This code runs when the script is executed directly.")
    
    # You can call other functions from here
    greet_user("Alice")

def greet_user(name):
    """
    A helper function to greet a user.
    """
    print(f"Hello, {name}!")

if __name__ == "__main__":
    # This block is executed when the script is run directly
    main()
