import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.markdown import Markdown
from utils import validate_and_check_ip, get_ip_metadata, hash_password, mask_email

console = Console()

def display_header():
    console.print(Panel.fit("[bold cyan]IP & Data Security Tool[/bold cyan]", border_style="cyan"))
    console.print("[dim]A privacy-focused tool for IP analysis and data handling.[/dim]\n")

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

def handle_password_hashing():
    console.print("\n[bold yellow]--- Password Hashing (SHA-256) ---[/bold yellow]")
    password = Prompt.ask("Enter plain-text password", password=True)
    
    if not password:
        console.print("[red]Password cannot be empty.[/red]")
        return
        
    hashed = hash_password(password)
    console.print(Panel(f"[bold]SHA-256 Hash:[/bold]\n[green]{hashed}[/green]", title="Result", expand=False))
    console.print("[dim]Note: Hashing performed locally.[/dim]")

def handle_email_masking():
    console.print("\n[bold yellow]--- Email Masking ---[/bold yellow]")
    email = Prompt.ask("Enter email address")
    
    is_valid, result = mask_email(email)
    
    if is_valid:
        console.print(f"Original: [dim]{email}[/dim]")
        console.print(f"Masked:   [bold green]{result}[/bold green]")
    else:
        console.print(f"[bold red]Error:[/bold red] {result}")

def main():
    while True:
        display_header()
        
        console.print("1. [bold]IP Metadata Lookup[/bold]")
        console.print("2. [bold]Password Hashing[/bold]")
        console.print("3. [bold]Email Masking[/bold]")
        console.print("4. [bold red]Exit[/bold red]")
        
        choice = Prompt.ask("\nSelect an option", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            handle_ip_lookup()
        elif choice == "2":
            handle_password_hashing()
        elif choice == "3":
            handle_email_masking()
        elif choice == "4":
            console.print("Exiting...")
            break
            
        console.print("\n" + "-" * 30 + "\n")
        # Optional: wait for user input before clearing or looping? 
        # For a simple CLI, just looping is fine.

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user. Exiting...[/bold red]")
        sys.exit(0)
