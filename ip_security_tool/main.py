import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from utils import (
    validate_and_check_ip, 
    get_ip_metadata, 
    mask_email, 
    load_or_generate_key, 
    encrypt_data, 
    decrypt_data
)

console = Console()

# Load encryption key at startup
try:
    ENCRYPTION_KEY = load_or_generate_key()
except Exception as e:
    console.print(f"[bold red]Critical Error:[/bold red] Could not load encryption key: {e}")
    sys.exit(1)

def display_header():
    console.print(Panel.fit("[bold cyan]IP & Data Security Tool[/bold cyan]", border_style="cyan"))
    console.print("[dim]A privacy-focused tool for IP analysis and secure data handling.[/dim]")
    console.print(f"[dim]Encryption Key Loaded (Worker Access Only)[/dim]\n")

def handle_ip_lookup():
    console.print("\n[bold yellow]--- IP Lookup (Public Only) ---[/bold yellow]")
    ip_input = Prompt.ask("Enter IPv4 or IPv6 address")
    
    is_valid, is_public, result = validate_and_check_ip(ip_input)
    
    if not is_valid:
        console.print(f"[bold red]Error:[/bold red] {result}")
        return

    console.print(f"IP Address: [green]{result}[/green]")
    
    if not is_public:
        console.print("[bold red]This is a Private/Local IP.[/bold red]")
        console.print("Metadata lookup is skipped for private IPs to prevent leakage or invalid queries.")
        return

    console.print("[green]Valid Public IP detected.[/green] Fetching metadata...")
    
    data = get_ip_metadata(str(result))
    
    if data.get("status") == "fail":
        console.print(f"[bold red]Lookup Failed:[/bold red] {data.get('message', 'Unknown error')}")
    else:
        table = Table(title="IP Metadata (No Location)", show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("ISP", data.get("isp", "N/A"))
        table.add_row("Organization", data.get("org", "N/A"))
        table.add_row("AS", data.get("as", "N/A"))
        table.add_row("IP Version", f"v{result.version}")
        
        console.print(table)

def handle_encryption_decryption():
    console.print("\n[bold yellow]--- Secure Data Encryption (Reversible) ---[/bold yellow]")
    console.print("Encrypt passwords or emails securely. Only the worker with the key file can decrypt.")
    
    action = Prompt.ask("Select Action", choices=["encrypt", "decrypt"], default="encrypt")
    
    if action == "encrypt":
        text_to_encrypt = Prompt.ask("Enter text to encrypt (Password/Email)", password=True)
        if not text_to_encrypt:
            console.print("[red]Input cannot be empty.[/red]")
            return
            
        encrypted = encrypt_data(text_to_encrypt, ENCRYPTION_KEY)
        console.print(Panel(f"[bold]Encrypted Data:[/bold]\n[green]{encrypted}[/green]", title="Result", expand=False))
        console.print("[dim]Save this string. It can only be decrypted with the 'secret.key' file.[/dim]")
        
    elif action == "decrypt":
        text_to_decrypt = Prompt.ask("Enter encrypted string")
        if not text_to_decrypt:
            console.print("[red]Input cannot be empty.[/red]")
            return
            
        success, result = decrypt_data(text_to_decrypt, ENCRYPTION_KEY)
        
        if success:
            console.print(Panel(f"[bold]Decrypted Data:[/bold]\n[green]{result}[/green]", title="Success", expand=False))
        else:
            console.print(f"[bold red]Decryption Failed:[/bold red] {result}")
            console.print("[dim]Ensure you are using the correct key file and the data is valid.[/dim]")

def handle_email_masking():
    console.print("\n[bold yellow]--- Email Visualization (Masking) ---[/bold yellow]")
    email = Prompt.ask("Enter email address")
    
    is_valid, result = mask_email(email)
    
    if is_valid:
        console.print(f"Original: [dim]{email}[/dim]")
        console.print(f"Masked:   [bold green]{result}[/bold green]")
        console.print("\n[dim]To encrypt this email securely, use option 2.[/dim]")
    else:
        console.print(f"[bold red]Error:[/bold red] {result}")

def main():
    while True:
        display_header()
        
        console.print("1. [bold]IP Metadata Lookup[/bold]")
        console.print("2. [bold]Secure Encryption/Decryption[/bold] (Passwords & Emails)")
        console.print("3. [bold]Email Visualization[/bold] (Masking)")
        console.print("4. [bold red]Exit[/bold red]")
        
        choice = Prompt.ask("\nSelect an option", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            handle_ip_lookup()
        elif choice == "2":
            handle_encryption_decryption()
        elif choice == "3":
            handle_email_masking()
        elif choice == "4":
            console.print("Exiting...")
            break
            
        console.print("\n" + "-" * 30 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user. Exiting...[/bold red]")
        sys.exit(0)
