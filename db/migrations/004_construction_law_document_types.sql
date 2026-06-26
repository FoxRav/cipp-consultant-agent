INSERT INTO ref.document_types (code, label, description) VALUES
    ('law_rakentamislaki_751_2023', 'Rakentamislaki 751/2023', 'Rakentamislaki Finlex Open Data -raakadatasta'),
    ('law_alueidenkayttolaki_132_1999', 'Alueidenkäyttölaki / maankäyttö- ja rakennuslaki 132/1999', 'Alueidenkäyttölaki / maankäyttö- ja rakennuslaki Finlex Open Data -raakadatasta')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

