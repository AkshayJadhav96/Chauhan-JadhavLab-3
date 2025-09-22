# Lab Assignment 3: UDP Client-Server Application

This project implements a client-server data transfer application using a custom UDP Application Protocol (UAP). The protocol supports sessions, handles different message types (`HELLO`, `DATA`, `ALIVE`, `GOODBYE`), and manages client-server interaction based on a Finite State Automaton (FSA).

The assignment explores two different approaches to handling concurrency: **Thread-based Concurrency** and **Event-driven (Non-blocking) Concurrency**.

## Partner Roles

The work was divided between two partners, A and B, to ensure experience with both concurrency models:

  * **Partner A:**

      * **Client:** Implemented using a **Thread-based** model.
      * **Server:** Implemented using a **Non-threaded (Event-driven)** model with `asyncio`.

  * **Partner B:**

      * **Client:** Implemented using a **Non-threaded (Event-driven)** model with `asyncio`.
      * **Server:** Implemented using a **Thread-based** model.

This structure ensures that all four combinations of client and server implementations can interoperate correctly.

## Directory Structure

The project is organized into the following directory structure as required by the assignment:

```
Chauhan-JadhavLab-3/
├── A/
│   ├── Client_T/      # Partner A's Threaded Client
│   ├── Server_NT/     # Partner A's Non-Threaded Server
|   ├── server
|   └── client     
├── B/
│   ├── client_code/   # Partner B's Non-Threaded Client
│   ├── server_code/   # Partner B's Threaded Server
│   ├── protocol/   # Partner B's messaging protocol 
|   ├── server
|   └── client     
└── readme.md
```

## How to Run the Code

Wrapper bash scripts (`server` and `client`) are provided in both the `A` and `B` directories to simplify execution and conform to the assignment's invocation standards.

### Prerequisites

  * Python 3.7+
  * A Unix-like environment (Linux, macOS, WSL)

### Instructions

1.  **Navigate to a Partner's Directory:** Open your terminal and change into either the `A` or `B` directory.

    ```bash
    cd Chauhan-JadhavLab-3/A/
    # or
    cd Chauhan-JadhavLab-3/B/
    ```

2.  **Make Scripts Executable:** Run this command once in each directory (`A` and `B`) to grant execute permissions to the wrapper scripts.

    ```bash
    chmod +x server client
    ```

3.  **Start the Server:** Launch the server, specifying a port number. It will wait for incoming client connections.

    ```bash
    # Example for running Partner A's server
    ./server 12345
    ```

4.  **Start the Client:** In a separate terminal, launch the client, providing the hostip (e.g., `127.0.0.1` if on same machine) and the port number used by the server.

    ```bash
    # Example for running Partner B's client
    ./client 127.0.0.1 12345
    ```

The client will now accept input from the keyboard. You can type messages and press Enter to send them to the server. To shut down the client, type `q` and press Enter, or press `Ctrl+D` to signal End-of-File (EOF). Also you can use same commands to shut down the server. 
