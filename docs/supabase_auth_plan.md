# Supabase Auth Planning

Tämä on suunnitelma, ei tuotantototeutus. CIPP Consultant Agentin pääjärjestelmä pysyy omassa PostgreSQL/FastAPI-putkessa. Supabasea harkitaan vain käyttäjärekisteröintiin, login/logoutiin, session/JWT-kontekstiin, user profileen ja myöhemmin mahdollisesti käyttäjäkohtaisen `user_case`-asetuksen tallennukseen.

## Rajaus v0.7.x-vaiheessa

Toteutettu:

- frontendin auth-adapterirajapinta
- mock auth -adapteri localStorage-sessionilla
- login/register/logout UI -prototyyppi
- session tokenin optionaalinen välitys `/api/answer`-kutsun Authorization-headerissa
- Supabase-adapterin stub, joka ei vielä kutsu Supabasea

Ei toteuteta vielä:

- multi-tenant organisaatiot
- maksut tai billing
- tuotanto-SaaS
- täysi RLS-politiikkamalli
- oikea Supabase client -kytkentä
- Supabase-avainten lisääminen repoon

## Periaatepäätös

Oma CIPP-tietokanta jää pääjärjestelmäksi:

```text
CIPP PostgreSQL/FastAPI
  -> project documents
  -> legal guidance
  -> KG
  -> retrieval
  -> source-grounded composer
```

Supabase jää alkuvaiheessa auth- ja session-palveluksi:

```text
Supabase Auth
  -> register
  -> login/logout
  -> session/JWT
  -> user profile
  -> later: saved user_case presets
```

## Adapterirakenne

Frontend käyttää `AuthAdapter`-rajapintaa:

```text
getSession()
signIn()
register()
signOut()
```

Nykyiset toteutukset:

- `mockAuthAdapter.ts`: paikallinen prototyyppi ilman verkkoa
- `supabaseAuthAdapter.ts`: suunniteltu stub, joka estää vahinkokäytön
- `authAdapter.ts`: valitsee providerin `VITE_AUTH_PROVIDER`-asetuksesta

Mock on oletus:

```env
VITE_AUTH_PROVIDER=mock
```

Supabase-prototyyppiä varten tarvittavat asetukset myöhemmin:

```env
VITE_AUTH_PROVIDER=supabase
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

Oikeita `.env`-tiedostoja tai Supabase-avaimia ei commitoida.

## Supabase-huomiot

Supabasen oma dokumentaatio määrittelee MAU-laskennan käyttäjiksi, jotka kirjautuvat tai refresh-tokenoivat laskutuskauden aikana. Free-planin MAU-kiintiö on dokumentaation mukaan 50 000, ja yli menevä hinnoittelu koskee maksullisia suunnitelmia kiintiön yli.

Lähde: [Supabase monthly active users documentation](https://supabase.com/docs/guides/platform/manage-your-usage/monthly-active-users)

Supabase Auth käyttää rate-limitejä auth-endpointtien väärinkäytön estämiseen, ja osa rajoista on projektissa konfiguroitavissa. Email-providerin rajoitteet pitää tarkistaa ennen oikeaa register-flowta, erityisesti jos käytetään Supabasen sisäänrakennettua sähköpostilähetystä custom SMTP:n sijaan.

Lähde: [Supabase Auth rate limits documentation](https://supabase.com/docs/guides/auth/rate-limits)

## Seuraava toteutusaskel

Seuraava turvallinen askel on backendin auth-verification adapter:

```text
Authorization: Bearer <jwt>
  -> verify via configured provider
  -> attach user context
  -> keep anonymous local-dev mode available
```

Vasta sen jälkeen kannattaa päättää, tallennetaanko user profile tai user_case Supabaseen, omaan CIPP-kantaan vai molempiin.

