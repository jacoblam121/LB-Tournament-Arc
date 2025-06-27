# Hybrid Commands Documentation

## Overview

Hybrid commands in discord.py work as both **prefix commands** (`!command`) and **slash commands** (`/command`). This document provides patterns and best practices for implementing dual-mode commands in the Tournament Bot.

## Key Concepts

### What are Hybrid Commands?

Hybrid commands use the `@commands.hybrid_command()` decorator and automatically register as both:
- **Prefix Commands**: Traditional `!command arg1 arg2` syntax
- **Slash Commands**: Modern `/command arg1:value arg2:value` syntax

### Core Challenge: Argument Parsing

Discord slash commands have **strict parameter requirements** that don't map directly to flexible prefix command patterns:

| Prefix Command | Slash Command Issue |
|---|---|
| `*args` (variable arguments) | ❌ Not supported |
| `*users: discord.Member` | ❌ Not supported |
| `ctx.message.mentions` | ❌ Only works for prefix |
| Complex parsing | ❌ Requires predefined parameters |

## Implementation Patterns

### Pattern 1: String Parameter + Internal Parsing

**Use Case**: Commands that need variable arguments or complex parsing

```python
@commands.hybrid_command(name="ffa", description="Create FFA match")
@app_commands.describe(players="Players for the match (space-separated mentions)")
async def ffa(self, ctx, *, players: str):
    """
    Works as:
    - Prefix: !ffa @user1 @user2 @user3
    - Slash: /ffa players:@user1 @user2 @user3
    """
    # Parse string into member list
    members = await self._parse_members_from_string(ctx, players)
    # Continue with existing logic...
```

### Pattern 2: Simple Parameter Mapping

**Use Case**: Commands with straightforward arguments

```python
@commands.hybrid_command(name="ping", description="Test bot response")
async def ping(self, ctx):
    """
    Works as:
    - Prefix: !ping
    - Slash: /ping
    """
    await ctx.send("🏓 Pong!")
```

### Pattern 3: Mixed Simple + Complex Parameters

**Use Case**: Commands with some fixed and some variable parameters

```python
@commands.hybrid_command(name="match-report", description="Report match results")
@app_commands.describe(
    match_id="Match ID to report results for",
    placements="Player placements (e.g., '@user1:1 @user2:2')"
)
async def match_report(self, ctx, match_id: int, *, placements: str):
    """
    Works as:
    - Prefix: !match-report 42 @user1:1 @user2:2 @user3:3
    - Slash: /match-report match_id:42 placements:@user1:1 @user2:2 @user3:3
    """
    # Parse placement string
    # Continue with existing logic...
```

## Essential Helper Methods

### Member Parsing Helper

```python
import shlex
from discord.ext import commands
from typing import List

async def _parse_members_from_string(self, ctx, text: str) -> List[discord.Member]:
    """
    Robust member parsing for hybrid commands.
    
    Handles:
    - Discord mentions (@user)
    - User IDs (123456789)
    - Usernames (JohnDoe)
    - Names with spaces ("John Doe")
    """
    if not text.strip():
        return []
    
    members = []
    converter = commands.MemberConverter()
    
    try:
        # Use shlex for robust splitting (handles quotes)
        potential_members = shlex.split(text)
    except ValueError:
        # Fallback for unmatched quotes
        potential_members = text.split()
    
    for arg in potential_members:
        try:
            member = await converter.convert(ctx, arg)
            if member not in members:  # Avoid duplicates
                members.append(member)
        except commands.MemberNotFound:
            # Skip non-member arguments
            continue
    
    return members
```

### Error Handling Pattern

```python
@commands.hybrid_command(name="example")
async def example(self, ctx, *, args: str):
    try:
        # Command logic here
        pass
    except ValueError as e:
        embed = discord.Embed(
            title="❌ Invalid Input",
            description=str(e),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, ephemeral=True)  # ephemeral for slash
    except Exception as e:
        self.logger.error(f"Unexpected error in {ctx.command}: {e}", exc_info=True)
        await ctx.send("❌ An unexpected error occurred.", ephemeral=True)
```

## Migration Checklist

When converting existing prefix commands to hybrid:

### Pre-Migration
- [ ] **Read existing command** to understand argument patterns
- [ ] **Identify parsing complexity** (simple args vs complex parsing)
- [ ] **Document current behavior** for regression testing
- [ ] **Check for ctx.message usage** (needs alternative for slash)

### Migration Steps
- [ ] **Add app_commands import** to file
- [ ] **Change decorator** from `@commands.command()` to `@commands.hybrid_command()`
- [ ] **Add @app_commands.describe()** for parameter documentation
- [ ] **Convert complex args** to string parameters
- [ ] **Update argument parsing** to use helper methods
- [ ] **Test both command types** thoroughly

### Post-Migration Validation
- [ ] **Prefix command still works** exactly as before
- [ ] **Slash command appears** in Discord picker
- [ ] **Parameter descriptions** are clear and helpful
- [ ] **Error handling** works for both command types
- [ ] **Auto-complete** works (if implemented)

## Best Practices

### 1. Parameter Naming
```python
# Good: Clear parameter names
@app_commands.describe(players="Players to include in the match")
async def ffa(self, ctx, *, players: str):

# Bad: Unclear parameter names
async def ffa(self, ctx, *, args: str):
```

### 2. Documentation
```python
@commands.hybrid_command(name="ffa", description="Create FFA match")
@app_commands.describe(players="Players for the match (space-separated mentions)")
async def ffa(self, ctx, *, players: str):
    """Create a Free-For-All match with mentioned players.
    
    Usage:
    - Prefix: !ffa @user1 @user2 @user3
    - Slash: /ffa players:@user1 @user2 @user3
    
    Args:
        players: Space-separated list of player mentions
    """
```

### 3. Error Messages
```python
# Good: Helpful for both command types
if not members:
    embed = discord.Embed(
        title="❌ No Players Found",
        description="Please mention players for the match.",
        color=discord.Color.red()
    )
    embed.add_field(
        name="Examples",
        value="• `!ffa @user1 @user2`\n• `/ffa players:@user1 @user2`",
        inline=False
    )
    await ctx.send(embed=embed)
```

### 4. Backwards Compatibility
```python
# Ensure existing prefix usage still works
def test_prefix_compatibility():
    # !ffa @user1 @user2 @user3
    # Should work exactly like before migration
    pass
```

## Common Pitfalls

### 1. ctx.message Dependencies
```python
# Bad: Only works for prefix commands
mentioned_users = ctx.message.mentions

# Good: Works for both command types
members = await self._parse_members_from_string(ctx, players)
```

### 2. Complex Argument Signatures
```python
# Bad: Won't work as slash command
async def ffa(self, ctx, *users: discord.Member):

# Good: Single string parameter
async def ffa(self, ctx, *, players: str):
```

### 3. Missing Parameter Descriptions
```python
# Bad: No help for slash command users
@commands.hybrid_command()
async def ffa(self, ctx, *, players: str):

# Good: Clear descriptions
@commands.hybrid_command(description="Create FFA match")
@app_commands.describe(players="Players for the match")
async def ffa(self, ctx, *, players: str):
```

## Testing Strategies

### Manual Testing
1. **Test prefix version**: `!command args`
2. **Test slash version**: `/command args`
3. **Test edge cases**: Empty args, invalid mentions, etc.
4. **Test error handling**: Both command types should show helpful errors

### Automated Testing
```python
async def test_hybrid_command():
    # Test prefix command
    ctx = MockContext(message_content="!ffa @user1 @user2")
    await cog.ffa(ctx, players="@user1 @user2")
    
    # Test slash command
    interaction = MockInteraction()
    await cog.ffa(interaction, players="@user1 @user2")
```

## Example Conversions

### Simple Command (No Changes Needed)
```python
# Before
@commands.command()
async def ping(self, ctx):
    await ctx.send("Pong!")

# After
@commands.hybrid_command(description="Test bot response")
async def ping(self, ctx):
    await ctx.send("Pong!")
```

### Complex Command (String Parsing)
```python
# Before
@commands.command()
async def ffa(self, ctx, *users: discord.Member):
    # Logic using users list

# After
@commands.hybrid_command(description="Create FFA match")
@app_commands.describe(players="Players for the match")
async def ffa(self, ctx, *, players: str):
    users = await self._parse_members_from_string(ctx, players)
    # Same logic using users list
```

## Conclusion

Hybrid commands provide the best of both worlds - familiar prefix commands for existing users and modern slash commands for new users. The key is robust string parsing and maintaining backwards compatibility.

Use this documentation as a reference when implementing new hybrid commands or converting existing ones.