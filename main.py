import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import datetime
import random
import sqlite3
import traceback

# ======================================================
#  CONFIGURAÇÃO DO BOT
# ======================================================
TOKEN = "SEU_TOKEN_AQUI"  # <-- Substitua pelo seu token aqui
PREFIX = "!"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ======================================================
#  BANCO DE DADOS (SQLite)
# ======================================================
con = sqlite3.connect("database.db")
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT,
    data TEXT,
    horario TEXT,
    descricao TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS presencas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id INTEGER,
    usuario TEXT,
    status TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS ranking (
    user_id INTEGER PRIMARY KEY,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0
)
""")

con.commit()

# ======================================================
#  STATUS ROTATIVO
# ======================================================
status_msgs = [
    "Criado por TX",
    "Sistema PRO v3",
    "O mestre dos bots",
    "Rankings carregados",
    "Eventos salvos no banco"
]

@tasks.loop(seconds=5)
async def mudar_status():
    msg = random.choice(status_msgs)
    await bot.change_presence(activity=discord.Game(name=msg))


# ======================================================
#  DADOS DE DUELOS
# ======================================================
# Estrutura: duelos[text_channel_id] = {
#   "modo": "1v1",
#   "callA_id": 123,
#   "callB_id": 456,
#   "owner_id": 111111
# }
duelos = {}

# ======================================================
#  BOT ONLINE
# ======================================================
@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")
    if not mudar_status.is_running():
        mudar_status.start()


# ======================================================
#  SISTEMA DE EVENTOS (BANCO)
# ======================================================
@bot.command(name="criar_evento")
async def criar_evento(ctx, tipo: str, data: str, horario: str, canal_mencao: discord.TextChannel, *, descricao: str = "Sem descrição"):
    try:
        # Valida a data
        datetime.datetime.strptime(data, "%d/%m/%Y")

        # Salva no banco
        cur.execute(
            "INSERT INTO eventos (tipo, data, horario, descricao) VALUES (?, ?, ?, ?)",
            (tipo, data, horario, descricao)
        )
        con.commit()

        # Mensagem principal no canal do comando
        await ctx.send(
            f"✅ Evento criado!\n"
            f"📅 {tipo} — {data} às {horario}\n"
            f"📝 {descricao}\n"
            f"📢 *Menção enviada em:* {canal_mencao.mention}"
        )

        # Envia a menção no canal escolhido
        await canal_mencao.send(
            f"📢 **NOVO EVENTO MARCADO!**\n\n"
            f"📅 **{tipo}** — {data} às {horario}\n"
            f"📝 {descricao}\n"
            f"👤 Criado por: {ctx.author.mention}"
        )

    except:
        await ctx.send("❌ Formato de data inválido! Use: **25/10/2025**")  

@bot.command(name="agenda")
async def agenda(ctx, periodo: str = "semana"):
    hoje = datetime.date.today()
    eventos = list(cur.execute("SELECT * FROM eventos"))
    if not eventos:
        return await ctx.send("📭 Nenhum evento no banco de dados.")
    resposta = ""
    limite = 7 if periodo == "semana" else 30
    fim = hoje + datetime.timedelta(days=limite)
    for id_, tipo, data, horario, desc in eventos:
        d = datetime.datetime.strptime(data, "%d/%m/%Y").date()
        if hoje <= d <= fim:
            resposta += f"**{id_}. {tipo}** — {data} às {horario}\n📝 {desc}\n\n"
    if not resposta:
        resposta = "📭 Nenhum evento neste período."
    await ctx.send(f"📅 **Agenda ({periodo})**\n\n{resposta}")


@bot.command(name="presenca")
async def presenca(ctx, id_evento: int):
    cur.execute(
        "INSERT INTO presencas (evento_id, usuario, status) VALUES (?, ?, ?)",
        (id_evento, ctx.author.name, "presente")
    )
    con.commit()
    await ctx.send(f"✅ {ctx.author.name} marcado como **presente** no evento {id_evento}.")


@bot.command(name="ausencia")
async def ausencia(ctx, id_evento: int):
    cur.execute(
        "INSERT INTO presencas (evento_id, usuario, status) VALUES (?, ?, ?)",
        (id_evento, ctx.author.name, "ausente")
    )
    con.commit()
    await ctx.send(f"🚫 {ctx.author.name} marcado como **ausente** no evento {id_evento}.")


@bot.command(name="lista")
async def lista(ctx, id_evento: int):
    dados = list(cur.execute("SELECT usuario, status FROM presencas WHERE evento_id=?", (id_evento,)))
    presentes = [u for u, s in dados if s == "presente"]
    ausentes = [u for u, s in dados if s == "ausente"]
    await ctx.send(
        f"📋 **Lista do evento {id_evento}:**\n"
        f"✅ Presentes: {', '.join(presentes) if presentes else 'Ninguém'}\n"
        f"🚫 Ausentes: {', '.join(ausentes) if ausentes else 'Ninguém'}"
    )


@bot.command(name="delete_evento")
async def delete_evento(ctx, id_evento: int):
    cur.execute("DELETE FROM eventos WHERE id=?", (id_evento,))
    cur.execute("DELETE FROM presencas WHERE evento_id=?", (id_evento,))
    con.commit()
    await ctx.send(f"🗑️ Evento {id_evento} removido!")


# ======================================================
#  COMANDO: !criasala  -> cria text channel (everyone vê) + envia embed com botões
# ======================================================
@bot.command(name="criasala")
async def criasala(ctx):
    guild = ctx.guild
    owner = ctx.author

    # cria o canal de texto onde everyone pode VER (para permitir menções), mas não enviar mensagens
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    sala = await guild.create_text_channel(
        f"duelo-{owner.name}",
        overwrites=overwrites
    )

    await ctx.send(f"🔧 Sala criada: {sala.mention}")

    modos = ["1v1", "2v2", "3v3", "4v4", "5v5", "6v6"]
    view = View()

    for modo in modos:
        btn = Button(label=modo, style=discord.ButtonStyle.primary)

        async def callback(interaction, modo=modo):
            # só o dono pode criar as calls? vamos permitir quem clicou (interaction.user) como responsável
            try:
                # Cria duas voice channels separadas (A e B) e nega view a everyone
                callA = await guild.create_voice_channel(
                    f"call-A-{modo}",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)}
                )
                callB = await guild.create_voice_channel(
                    f"call-B-{modo}",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)}
                )

                # garante que o usuário que clicou tenha acesso inicialmente (para poder entrar se quiser)
                await callA.set_permissions(interaction.user, view_channel=True, connect=True, speak=True)
                await callB.set_permissions(interaction.user, view_channel=True, connect=True, speak=True)

                # salva info do duelo - chave é o text channel (sala) onde o botão foi clicado
                duelos[interaction.channel.id] = {
                    "modo": modo,
                    "callA_id": callA.id,
                    "callB_id": callB.id,
                    "owner_id": interaction.user.id
                }

                await interaction.response.send_message(
                    f"🎮 Modo **{modo}** selecionado!\n\n"
                    f"Agora envie no canal **{interaction.channel.mention}** as menções no formato:\n\n"
                    f"**Time A:** @j1 @j2 ...\n"
                    f"**Time B:** @j1 @j2 ...\n\n"
                    f"O bot vai aplicar permissão para cada membro entrar na sua call correspondente e tentar movê-los se estiverem em uma call.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(f"⚠️ Erro ao criar calls: {e}", ephemeral=True)

        btn.callback = callback
        view.add_item(btn)

    await sala.send("⚔️ **Escolha o modo de duelo:** (Clique em um botão)", view=view)


# ======================================================
#  Funções auxiliares para ranking / finalizar
# ======================================================
async def registrar_vitoria(winners, losers):
    for member in winners:
        cur.execute("INSERT OR IGNORE INTO ranking (user_id, wins, losses) VALUES (?, 0, 0)", (member.id,))
        cur.execute("UPDATE ranking SET wins = wins + 1 WHERE user_id=?", (member.id,))
    for member in losers:
        cur.execute("INSERT OR IGNORE INTO ranking (user_id, wins, losses) VALUES (?, 0, 0)", (member.id,))
        cur.execute("UPDATE ranking SET losses = losses + 1 WHERE user_id=?", (member.id,))
    con.commit()


async def finalizar_sala(canal_id, guild):
    dados = duelos.pop(canal_id, None)
    if not dados:
        return False

    callA = guild.get_channel(dados.get("callA_id"))
    callB = guild.get_channel(dados.get("callB_id"))
    canal = guild.get_channel(canal_id)

    try:
        if callA:
            await callA.delete()
        if callB:
            await callB.delete()
        if canal:
            await canal.delete()
    except Exception:
        # ignore erros ao deletar (permissões)
        pass

    return True


# ======================================================
#  COMANDO: !finalizar [#canal/opcional]  -> Finaliza duelo manualmente
# ======================================================
@bot.command(name="finalizar")
@commands.has_permissions(manage_channels=True)
async def finalizar(ctx, canal: discord.TextChannel = None):
    target_channel = canal or ctx.channel
    ended = await finalizar_sala(target_channel.id, ctx.guild)
    if ended:
        await ctx.send("✅ Duelo finalizado e canais removidos.")
    else:
        await ctx.send("❌ Não encontrei um duelo ativo nesse canal.")


# ======================================================
#  ON_MESSAGE — PROCESSA TIMES E BOTÕES DE VITÓRIA
# ======================================================
@bot.event
async def on_message(message):
    try:
        # evita que bots disparem
        if message.author.bot:
            return

        conteudo = message.content.lower()

        # ------------------------------
        #  Sistema de rank automático por texto
        # ------------------------------
        ranks = {
            "bronze": "🥉 Bronze",
            "prata": "🥈 Prata",
            "ouro": "🥇 Ouro",
            "diamante": "💎 Diamante",
            "pro": "🏆 Pro"
        }

        for chave, nome in ranks.items():
            if f"eu sou rank {chave}" in conteudo:
                cargo = discord.utils.get(message.guild.roles, name=nome)
                if not cargo:
                    cargo = await message.guild.create_role(name=nome)
                # remove outros ranks do autor
                for r in list(message.author.roles):
                    if r.name in ranks.values():
                        try:
                            await message.author.remove_roles(r)
                        except Exception:
                            pass
                # adiciona o rank
                try:
                    await message.author.add_roles(cargo)
                except Exception:
                    pass
                await message.channel.send(f"✅ {message.author.mention} agora é **{nome}!**")

        # ------------------------------
        #  SISTEMA DE DUELOS: recebe menções e aplica permissões/movimenta
        #  Espera-se que a mensagem contenha "time a" e "time b" e mencione jogadores
        # ------------------------------
        if message.channel.id in duelos and "time a" in conteudo and "time b" in conteudo:
            dados = duelos[message.channel.id]
            callA = message.guild.get_channel(dados["callA_id"])
            callB = message.guild.get_channel(dados["callB_id"])
            mencoes = list(message.mentions)

            if len(mencoes) < 2:
                return await message.reply("❌ Marque jogadores suficientes (pelo menos 2 menções).")

            metade = len(mencoes) // 2
            timeA = mencoes[:metade]
            timeB = mencoes[metade:]

            # aplica permissões por membro (cada um ganha acesso apenas à sua call)
            for membro in timeA:
                try:
                    await callA.set_permissions(membro, view_channel=True, connect=True, speak=True)
                    # remove acesso à callB caso tenha
                    await callB.set_permissions(membro, view_channel=False, connect=False, speak=False)
                except Exception:
                    pass

            for membro in timeB:
                try:
                    await callB.set_permissions(membro, view_channel=True, connect=True, speak=True)
                    await callA.set_permissions(membro, view_channel=False, connect=False, speak=False)
                except Exception:
                    pass

            # tenta mover jogadores que já estão em alguma voz para suas calls
            for m in timeA:
                try:
                    if m.voice and callA:
                        await m.move_to(callA)
                except Exception:
                    pass
            for m in timeB:
                try:
                    if m.voice and callB:
                        await m.move_to(callB)
                except Exception:
                    pass

            # resposta com botões de vitória
            await message.reply(
                f"✔️ Times organizados!\n"
                f"🟥 **Time A:** {', '.join(u.mention for u in timeA)}\n"
                f"🟦 **Time B:** {', '.join(u.mention for u in timeB)}\n\n"
                f"Escolha o vencedor usando os botões abaixo."
            )

            view = View()
            botaoA = Button(label="Vitória Time A", style=discord.ButtonStyle.success)
            botaoB = Button(label="Vitória Time B", style=discord.ButtonStyle.danger)

            async def winA(interaction):
                # só permitir clicarem se duelo ainda existir
                if message.channel.id not in duelos:
                    return await interaction.response.send_message("❌ Duelo já finalizado ou inválido.", ephemeral=True)
                await registrar_vitoria(timeA, timeB)
                await interaction.response.send_message("🏆 Vitória do **Time A** registrada!")
                await finalizar_sala(message.channel.id, message.guild)

            async def winB(interaction):
                if message.channel.id not in duelos:
                    return await interaction.response.send_message("❌ Duelo já finalizado ou inválido.", ephemeral=True)
                await registrar_vitoria(timeB, timeA)
                await interaction.response.send_message("🏆 Vitória do **Time B** registrada!")
                await finalizar_sala(message.channel.id, message.guild)

            botaoA.callback = winA
            botaoB.callback = winB
            view.add_item(botaoA)
            view.add_item(botaoB)

            await message.channel.send(view=view)

        # permite que comandos prefix funcionem
        await bot.process_commands(message)

    except Exception as e:
        print("ERRO ON_MESSAGE:", e)
        print(traceback.format_exc())


# ======================================================
#  COMANDOS DE RANK VISUAL
# ======================================================
@bot.command(name="rank")
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = cur.execute("SELECT wins, losses FROM ranking WHERE user_id=?", (member.id,)).fetchone()
    if not data:
        return await ctx.send("📉 Esse usuário ainda não tem partidas.")
    wins, losses = data
    await ctx.send(f"🏅 **Ranking de {member.display_name}**\nVitórias: {wins}\nDerrotas: {losses}")


@bot.command(name="top")
async def top(ctx):
    lista = cur.execute("SELECT user_id, wins FROM ranking ORDER BY wins DESC").fetchall()
    if not lista:
        return await ctx.send("Sem jogadores ranqueados ainda.")
    msg = "🏆 **TOP JOGADORES**\n\n"
    pos = 1
    for user_id, wins in lista[:10]:
        user = ctx.guild.get_member(user_id)
        if user:
            msg += f"{pos}. **{user.display_name}** — {wins} vitórias\n"
            pos += 1
    await ctx.send(msg) 

# ======================================================
# RODAR BOT
# ======================================================
import os
TOKEN = os.getenv("TOKEN")

