#!/usr/bin/python
import argparse
import logging
import time
import sys
import traceback
import pdb
from custom_exceptions import GeneralPogoException

from api import PokeAuthSession
from location import Location

from pokedex import pokedex
from inventory import items


def setupLogger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def displayProfile(sess):
    s = ""
    s += sess.getProfile().player_data.username
    s += " Level:"
    inv = sess.getInventory()
    stats = inv.stats
    s += str(stats.level)
    s += " XP to next: "
    s += str(stats.next_level_xp - stats.experience)
    s += " Pokedex: "
    s += str(stats.unique_pokedex_entries)+"/151"
    s += " Party size: "
    s += str(len(inv.party))
    s += " Strongest: "
    if len(inv.party) > 0:
        s += str(getStrongestPokeInPartyString(inv.party))
    else:
        s += "NA"
    logging.info("(PROFILE)\t-\t"+s)

def getStrongestPokeInParty(party):
    strongest = 0
    ret = 0
    for poke in party:
        if poke.cp > strongest:
            strongest = poke.cp
            ret = poke
    return ret

def getStrongestPokeInPartyString(party):
    poke = getStrongestPokeInParty(party)
    return str(pokedex[poke.pokemon_id]) + " " + str(poke.cp) +" CP"

def findNearPokemon(session):
    cells = session.getMapObjects()
    pokemons = []
    for cell in cells.map_cells:
        pokemons += [p for p in cell.wild_pokemons]
    return pokemons

def showNearPokemon(session):
    pokemons = findNearPokemon(session)
    for pokemon in pokemons:
        print(pokemon)


# Wrap both for ease
def encounterAndCatch(session, pokemon, thresholdP=0.5, limit=5, delay=2):
    # Start encounter
    encounter = session.encounterPokemon(pokemon)

    # Grab needed data from proto
    chances = encounter.capture_probability.capture_probability
    balls = encounter.capture_probability.pokeball_type
    bag = session.checkInventory().bag

    # Have we used a razz berry yet?
    berried = False

    # Make sure we aren't oer limit
    count = 0

    # Attempt catch
    while True:
        bestBall = items.UNKNOWN
        altBall = items.UNKNOWN

        # Check for balls and see if we pass
        # wanted threshold
        for i in range(len(balls)):
            if balls[i] in bag and bag[balls[i]] > 0:
                altBall = balls[i]
                if chances[i] > thresholdP:
                    bestBall = balls[i]
                    break

        # If we can't determine a ball, try a berry
        # or use a lower class ball
        if bestBall == items.UNKNOWN:
            if not berried and items.RAZZ_BERRY in bag and bag[items.RAZZ_BERRY]:
                logging.info("(ENCOUNTER)\t-\tUsing a RAZZ_BERRY")
                session.useItemCapture(items.RAZZ_BERRY, pokemon)
                berried = True
                time.sleep(delay)
                continue

            # if no alt ball, there are no balls
            elif altBall == items.UNKNOWN:
                raise GeneralPogoException("(ENCOUNTER)\t-\tOut of usable balls")
            else:
                bestBall = altBall

        # Try to catch it!!
        logging.info("(ENCOUNTER)\t-\tUsing a %s" % items[bestBall])
        attempt = session.catchPokemon(pokemon, bestBall)
        time.sleep(delay)

        # Success or run away
        if attempt.status == 1:
            return attempt

        # CATCH_FLEE is bad news
        if attempt.status == 3:
            logging.info("(ENCOUNTER)\t-\tPossible soft ban.")
            return attempt

        # Only try up to x attempts
        count += 1
        if count >= limit:
            logging.info("(ENCOUNTER)\t-\tOver catch limit")
            return None


# Catch a pokemon at a given point
def walkAndCatch(session, pokemon, speed):
    if pokemon:
        logging.info("(ENCOUNTER)\t-\tCatching %s:" % pokedex[pokemon.pokemon_data.pokemon_id])
        session.walkTo(pokemon.latitude, pokemon.longitude, speed)
        r = encounterAndCatch(session, pokemon)
        if r.status == 1:
            pokes = session.checkInventory().party
            caughtpoke = {}
            for poke in pokes:
                if r.captured_pokemon_id == poke.id:
                    caughtpoke = poke
                    break
            logging.info("(ENCOUNTER)\t-\tCaught " + pokedex[caughtpoke.pokemon_id]+" with "+str(caughtpoke.cp)+" CP")
            return True
        else:
            logging.info("(ENCOUNTER)\t-\tGot away")
            return False



# Do Inventory stuff
def getInventory(session):
    logging.info("Get Inventory:")
    logging.info(session.getInventory())


# Basic solution to spinning all forts.
# Since traveling salesman problem, not
# true solution. But at least you get
# those step in
def sortCloseForts(session):
    # Sort nearest forts (pokestop)
    cells = session.getMapObjects()
    latitude, longitude, _ = session.getCoordinates()
    ordered_forts = []
    for cell in cells.map_cells:
        for fort in cell.forts:
            dist = Location.getDistance(
                latitude,
                longitude,
                fort.latitude,
                fort.longitude
            )
            if fort.type == 1:
                ordered_forts.append({'distance': dist, 'fort': fort})

    ordered_forts = sorted(ordered_forts, key=lambda k: k['distance'])
    return [instance['fort'] for instance in ordered_forts]


# Find the fort closest to user
def findClosestFort(session):
    # Find nearest fort (pokestop)
    for fort in sortCloseForts(session):
        if(fort.cooldown_complete_timestamp_ms > int(time.time()*1000)):
            continue
        return fort
    return False


# Walk to fort and spin
def walkAndSpin(session, fort, speed):
    # No fort, demo == over
    if fort:
        details = session.getFortDetails(fort)
        logging.info("(POKESTOP)\t-\tSpinning the Fort \"%s\":" % details.name)

        # Walk over
        session.walkTo(fort.latitude, fort.longitude, speed)
        # Give it a spin
        fortResponse = session.getFortSearch(fort)
        logging.info("(POKESTOP)\t-\tXP: %d" % fortResponse.experience_awarded)


# Walk and spin everywhere
def walkAndSpinMany(session, forts):
    for fort in forts:
        walkAndSpin(session, fort, speed)


# A very brute force approach to evolving
def evolveAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        logging.info(session.evolvePokemon(pokemon))
        time.sleep(1)


# You probably don't want to run this
def releaseAllPokemon(session):
    inventory = session.checkInventory()
    for pokemon in inventory.party:
        session.releasePokemon(pokemon)
        time.sleep(1)


# Just incase you didn't want any revives
def tossRevives(session):
    bag = session.checkInventory().bag
    return session.recycleItem(items.REVIVE, bag[items.REVIVE])


# Set an egg to an incubator
def setEgg(session):
    inventory = session.checkInventory()

    # If no eggs, nothing we can do
    if len(inventory.eggs) == 0:
        return None

    egg = inventory.eggs[0]
    incubator = inventory.incubators[0]
    return session.setEgg(incubator, egg)

def cleanInventory(session):
    recycled = 0
    bag = session.checkInventory().bag

    # Clear out all of a crtain type
    tossable = [items.POTION, items.SUPER_POTION, items.REVIVE]
    for toss in tossable:
        if toss in bag and bag[toss]:
            session.recycleItem(toss, bag[toss])
            recycled+=1

    # Limit a certain type
    limited = {
        items.POKE_BALL: 30,
        items.GREAT_BALL: 40,
        items.ULTRA_BALL: 100,
        items.RAZZ_BERRY: 50,
        items.HYPER_POTION: 0,
        items.MAX_POTION: 0,
        items.MAX_REVIVE: 0,
        items.MASTER_BALL: 300
    }
    for limit in limited:
        if limit in bag and bag[limit] > limited[limit]:
            session.recycleItem(limit, bag[limit] - limited[limit])
            recycled+=1
    logging.info("(ITEM MANAGE)\t-\tCleaned out Inventory, "+str(recycled)+" items recycled.")

def getPokesByID(party, id):
    ret = []
    for poke in party:
        if poke.pokemon_id == id:
            ret.append(poke)
    return ret

def cleanAllPokes(session):
    logging.info("(POKEMANAGE)\t-\tCleaning out Pokes...")
    party = session.checkInventory().party
    keepers = [pokedex.VAPOREON, pokedex.ARCANINE, pokedex.SNORLAX, pokedex.LAPRAS]
    # group
    for poke in range(0,151):
        if poke in keepers:
            continue
        pokz = getPokesByID(party, poke)
        if len(pokz) == 0:
            continue
        # order by cp
        ordered_pokz= sorted(pokz, key=lambda k: k.cp)
        #remove all but best CP and best IV
        for x in range(len(ordered_pokz)-1):
            pok = ordered_pokz[x]
            if pok.cp > 1500 or (pok.pokemon_id == pokedex.EEVEE and pok.cp > 600):
                continue
            logging.info("(POKEMANAGE)\t-\tReleasing: "+pokedex[pok.pokemon_id]+" "+str(pok.cp)+" CP")
            session.releasePokemon(pok)

def cleanPokes(session, pokemon_id):
    party = session.checkInventory().party
    keepers = [pokedex.VAPOREON, pokedex.ARCANINE, pokedex.SNORLAX, pokedex.LAPRAS]
    # group
    poke = pokemon_id
    if poke in keepers:
        return
    pokz = getPokesByID(party, poke)
    if len(pokz) == 0:
        return
    # order by cp
    ordered_pokz= sorted(pokz, key=lambda k: k.cp)
    #remove all but best CP and best IV
    for x in range(len(ordered_pokz)-1):
        pok = ordered_pokz[x]
        if pok.cp > 1500 or \
                (pok.pokemon_id == pokedex.EEVEE and pok.cp > 600) or \
                (pok.pokemon_id == pokedex.DRATINI and pok.cp > 700) or \
                (pok.pokemon_id == pokedex.DRAGONAIR and pok.cp > 1100):
            continue
        logging.info("(POKEMANAGE)\t-\tReleasing: "+pokedex[pok.pokemon_id]+" "+str(pok.cp)+" CP")
        session.releasePokemon(pok)

def catch_demPokez(pokez, sess, whatup_cunt):
    if walkAndCatch(sess, pokez, whatup_cunt):
        cleanAllPokes(sess)
        return True
    else:
        cleanAllPokes(sess)
        return False

def enough_time_left(pokzzzzzzzzz):
    return min(sorted(pokzzzzzzzzz, lambda p: p.time_till_hidden_ms)) > 1000

def safe_catch(pokies, session, speed): # NOT CAMEL CASE COZ PEP8 U FUCKERS
    """
    Performs a safe catch of good pokemanz by catching the shithouse ones first and only approaching the mad dogs once it's safe to do so (i.e. after you've catch_successed a shithouse one)
    """
    epicpokes = []
    shitpokes = []
    for pokemon in pokies:
        if pokedex.getRarityById(pokemon.pokemon_data.pokemon_id) >= 2: #if rare pokemanzzzz
            epicpokes.append(pokemon)
        else:
            shitpokes.append(pokemon)
    if epicpokes:
        logging.info("SOME EPIC POKES EYYYYY: {}".format("\n".join([repr(cunt.pokemon_data) for cunt in epicpokes])))
    if shitpokes:
        logging.info("THESE POKES SUCK A MASSIVE DICK: {}".format("\n".join([repr(cunt.pokemon_data) for cunt in shitpokes])))
    if epicpokes:
        while True:
            try:
                asshole = shitpokes.pop()
                if catch_demPokez(asshole, session, speed):
                    break
                else:
                    continue
            except IndexError:
                logging.info("Ran out of shithouse pokez")
                if enough_time_left(pokies):
                    return False
                else:
                    logging.info("well fuckit - no time to waste...")
                    break
        for spaz in epicpokes:
            catch_demPokez(spaz, session, speed)
    for pokemon in shitpokes:
        catch_demPokez(pokemon, session, speed)
    return True
#cam bot :D
def camBot(session):
    startlat, startlon, startalt = session.getCoordinates()
    cooldown = 10
    speed = 150*0.277778  # (150kph)
    # with open("GOOD_FUCKING_POKEMONZ.txt") as f:
    #     for line in f.readlines():
    #         line = line.strip()
    #         goodpokes.append(line)
    while True:
        try:
            lat, lon, alt = session.getCoordinates()
            dist = Location.getDistance(startlat, startlon,lat, lon)
            logging.info("(TRAVEL)\t-\tDistance from start: "+str(dist))
            if dist > 5000:
                print "(TRAVEL)\t-\tWalking back to start to stay in area"
                session.walkTo(startlat, startlon, speed)
            displayProfile(session)
            cleanAllPokes(session)
            # check for pokeballs (don't try to catch if we have none)
            bag = session.getInventory().bag
            if bag[items.POKE_BALL] > 0 or bag[items.GREAT_BALL] > 0 or bag[items.ULTRA_BALL] > 0 or bag[items.MASTER_BALL] > 0:
                coutn = 1
                while True:
                    if safe_catch(findNearPokemon(session), session, speed):
                        break
                    elif coutn >5:
                        break
            fort = findClosestFort(session)
            if fort:
                walkAndSpin(session, fort, speed)
                cleanInventory(session)
            # check distance from start
        # Catch problems and reauthenticate
        except GeneralPogoException as e:
            logging.critical('GeneralPogoException raised: %s', e)
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)

        except Exception as e:
            logging.critical('Exception raised: %s', e)
            traceback.print_exc()
            session = poko_session.reauthenticate(session)
            time.sleep(cooldown)

# Entry point
# Start off authentication and demo
if __name__ == '__main__':
    while(True):


        setupLogger()
        logging.debug('Logger set up')

        # Read in args
        parser = argparse.ArgumentParser()
        parser.add_argument("-a", "--auth", help="Auth Service", required=True)
        parser.add_argument("-u", "--username", help="Username", required=True)
        parser.add_argument("-p", "--password", help="Password", required=True)
        parser.add_argument("-l", "--location", help="Location")
        parser.add_argument("-g", "--geo_key", help="GEO API Secret")
        args = parser.parse_args()

        # Check service
        if args.auth not in ['ptc', 'google']:
            logging.error('Invalid auth service {}'.format(args.auth))
            sys.exit(-1)

        # Create PokoAuthObject
        poko_session = PokeAuthSession(
            args.username,
            args.password,
            args.auth,
            geo_key=args.geo_key
        )

        # Authenticate with a given location
        # Location is not inherent in authentication
        # But is important to session
        if args.location:
            session = poko_session.authenticate(locationLookup=args.location)
        else:
            session = poko_session.authenticate()

        # Time to show off what we can do
        if session:
            camBot(session)
            # General
    #        getProfile(session)
    #        getInventory(session)

            # Pokemon related
    #        pokemon = findBestPokemon(session)
    #        walkAndCatch(session, pokemon)

            # Pokestop related
    #        fort = findClosestFort(session)
    #        walkAndSpin(session, fort)

            # see simpleBot() for logical usecases
            # eg. simpleBot(session)

        else:
            logging.critical('Session not created successfully')
