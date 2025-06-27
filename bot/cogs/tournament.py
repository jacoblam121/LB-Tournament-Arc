import discord
from discord.ext import commands
from typing import Optional
from bot.config import Config
from bot.ui.views import EventBrowserView

class TournamentCog(commands.Cog):
    """Tournament information commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='list-clusters')
    async def list_clusters(self, ctx):
        """View all tournament clusters"""
        try:
            # Permission-based filtering: admin sees all, users see active only
            is_owner = ctx.author.id == Config.OWNER_DISCORD_ID
            clusters = await self.bot.db.get_all_clusters(active_only=not is_owner)
            
            if not clusters:
                description = "No clusters found." if is_owner else "No active clusters found."
                if is_owner:
                    description += " Use `/admin-populate-data` to load from CSV."
                embed = discord.Embed(
                    title="Tournament Clusters",
                    description=description,
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            # Create enhanced embed with admin features
            title = "Tournament Clusters"
            if is_owner:
                title += " (Admin View)"
            
            embed = discord.Embed(title=title, color=discord.Color.blue())
            
            cluster_list = []
            for cluster in clusters:
                # Admin sees status indicators, users see clean list
                if is_owner:
                    status = "🟢" if cluster.is_active else "🔴"
                    events_count = len(cluster.events) if cluster.events else 0
                    cluster_list.append(f"{status} **{cluster.number}.** {cluster.name} ({events_count} events)")
                else:
                    events_count = len([e for e in cluster.events if e.is_active]) if cluster.events else 0
                    cluster_list.append(f"**{cluster.number}.** {cluster.name} ({events_count} events)")
            
            # Split into chunks if too many clusters
            if len(cluster_list) <= 20:
                embed.description = "\n".join(cluster_list)
            else:
                embed.description = "\n".join(cluster_list[:20])
                embed.add_field(
                    name="Note", 
                    value=f"Showing first 20 of {len(cluster_list)} clusters", 
                    inline=False
                )
            
            # Admin-only footer information
            if is_owner:
                active_count = sum(1 for c in clusters if c.is_active)
                embed.set_footer(text=f"Total: {len(clusters)} clusters ({active_count} active)")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error listing clusters: {e}")
    
    @commands.hybrid_command(name='list-events')
    async def list_events(self, ctx, cluster_name: Optional[str] = None):
        """View events with interactive filtering and pagination"""
        try:
            # For slash commands, use the new interactive EventBrowserView
            if ctx.interaction:
                is_owner = ctx.author.id == Config.OWNER_DISCORD_ID
                initial_cluster_id = None

                # 1. Resolve cluster_name to cluster_id if provided
                if cluster_name:
                    cluster = await self.bot.db.get_cluster_by_name(cluster_name)
                    
                    # 2. Handle not found or inactive clusters for non-admins
                    if not cluster or (not cluster.is_active and not is_owner):
                        embed = discord.Embed(
                            title="❌ Cluster Not Found",
                            description=f"No active cluster found with the name: `{cluster_name}`",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed, ephemeral=True)
                        return
                    
                    initial_cluster_id = cluster.id

                # Initialize and start the interactive view with the ID
                view = EventBrowserView(self.bot, ctx.interaction, initial_cluster_id=initial_cluster_id)
                await view.start()
                return
            
            # For prefix commands, fall back to legacy static display with optional cluster filtering
            is_owner = ctx.author.id == Config.OWNER_DISCORD_ID
            
            if cluster_name:
                # Get specific cluster
                cluster = await self.bot.db.get_cluster_by_name(cluster_name)
                if not cluster:
                    embed = discord.Embed(
                        title="❌ Cluster Not Found",
                        description=f"No cluster found with name: `{cluster_name}`",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                events = await self.bot.db.get_all_events(cluster_id=cluster.id, active_only=not is_owner)
                title = f"Events in {cluster.name}"
                if is_owner:
                    title += " (Admin View)"
            else:
                # Get all events
                events = await self.bot.db.get_all_events(active_only=not is_owner)
                title = "All Tournament Events"
                if is_owner:
                    title += " (Admin View)"
            
            if not events:
                description = "No events found." if is_owner else "No active events found."
                description += f" in cluster `{cluster_name}`" if cluster_name else ""
                if is_owner and not cluster_name:
                    description += " Use `/admin-populate-data` to load from CSV."
                
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color.orange()
                )
                
                # Add helpful note about interactive version
                if not cluster_name:
                    embed.add_field(
                        name="💡 Tip",
                        value="Use `/list-events` (slash command) for interactive browsing with filters!",
                        inline=False
                    )
                
                await ctx.send(embed=embed)
                return
            
            # Legacy static display logic (simplified for prefix commands)
            embed = discord.Embed(title=title, color=discord.Color.blue())
            
            if cluster_name:
                # Single cluster view - show first 15 events
                event_list = []
                for i, event in enumerate(events[:15], 1):
                    if is_owner:
                        status = "🟢" if event.is_active else "🔴"
                        event_list.append(f"{status} **{i}.** {event.name} - {event.scoring_type}")
                    else:
                        event_list.append(f"**{i}.** {event.name} - {event.scoring_type}")
                
                embed.description = "\n".join(event_list)
                
                if len(events) > 15:
                    embed.add_field(
                        name="Note", 
                        value=f"Showing first 15 of {len(events)} events\nUse `/list-events` for full interactive browsing", 
                        inline=False
                    )
                    
                # Admin footer
                if is_owner:
                    active_count = sum(1 for e in events if e.is_active)
                    embed.set_footer(text=f"Total: {len(events)} events ({active_count} active)")
                    
            else:
                # All events - show summary by cluster
                cluster_events = {}
                for event in events:
                    cluster_name_key = event.cluster.name if event.cluster else "Unknown"
                    if cluster_name_key not in cluster_events:
                        cluster_events[cluster_name_key] = []
                    cluster_events[cluster_name_key].append(event)
                
                # Show first 8 clusters
                field_count = 0
                for cluster_name_key, cluster_event_list in list(cluster_events.items())[:8]:
                    event_summary = []
                    for event in cluster_event_list[:4]:  # Show first 4 events per cluster
                        if is_owner:
                            status = "🟢" if event.is_active else "🔴"
                            event_summary.append(f"{status} {event.name}")
                        else:
                            event_summary.append(f"{event.name}")
                    
                    if len(cluster_event_list) > 4:
                        event_summary.append(f"... +{len(cluster_event_list) - 4} more")
                    
                    # Field name with cluster status for admin
                    if is_owner:
                        cluster_obj = next((c for c in await self.bot.db.get_all_clusters(active_only=False) 
                                          if c.name == cluster_name_key), None)
                        if cluster_obj:
                            cluster_status = "🟢" if cluster_obj.is_active else "🔴"
                            field_name = f"{cluster_status} {cluster_name_key}"
                        else:
                            field_name = cluster_name_key
                    else:
                        field_name = cluster_name_key
                    
                    embed.add_field(
                        name=field_name,
                        value="\n".join(event_summary) if event_summary else "No events",
                        inline=True
                    )
                    field_count += 1
                
                # Summary note
                if len(cluster_events) > 8 or any(len(events) > 4 for events in cluster_events.values()):
                    embed.add_field(
                        name="💡 Interactive Browsing",
                        value="Use `/list-events` (slash command) for full interactive browsing with filters and pagination!",
                        inline=False
                    )
                
                # Admin footer
                if is_owner:
                    total_events = len(events)
                    active_events = sum(1 for e in events if e.is_active)
                    embed.set_footer(text=f"Total: {total_events} events ({active_events} active) across {len(cluster_events)} clusters")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error listing events: {e}")
    
    @commands.command(name='tournaments')
    async def list_tournaments(self, ctx):
        """List active tournaments"""
        embed = discord.Embed(
            title="🏆 Tournaments",
            description="Tournament system coming soon!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TournamentCog(bot))