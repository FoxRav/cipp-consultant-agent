INSERT INTO ref.document_types (code, label, description) VALUES
    ('attachment_index', 'Liiteluettelo', 'Sopimuspaketin erillinen liiteluettelo'),
    ('negotiation_attachment', 'Urakkaneuvottelupöytäkirjan liite', 'Urakkaneuvottelupöytäkirjan erillinen liite'),
    ('safety_plan', 'Työturvallisuus- tai työsuojelusuunnitelma', 'Työmaan turvallisuutta tai työsuojelua koskeva suunnitelma'),
    ('project_schedule', 'Aikataulu', 'Urakan tai työvaiheiden aikatauluasiakirja'),
    ('contractor_appendices', 'Urakoitsijan liitteet', 'Urakoitsijan sopimukseen liittämät täydentävät asiakirjat'),
    ('quality_plan', 'Toteutus- ja laadunhallintasuunnitelma', 'Työmaakohtainen toteutus- ja laadunhallintasuunnitelma'),
    ('project_note', 'Projektihuomio', 'Projektikansion vapaa tekstimuotoinen huomio')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

