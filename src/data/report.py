from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import REPORT_PATH


class ReportWriter:
    FIGURE_TEXT = {
        "F01": {
            "title": "Campos com dados em falta por ficha",
            "question": "Onde estão os buracos e quais campos são críticos?",
            "interpretation": "Ref, comentários e follow-up são os campos mais vazios; a ausência é sobretudo estrutural, não aleatória.",
            "n": "30 campos com missing",
            "denominator": "campos com pelo menos uma célula vazia",
            "source": "03_team_a_adoptions_spring_2026.xlsx; 04_team_b_followup_animals.csv",
            "caveat": "Campos 100% preenchidos não aparecem no gráfico; a tabela T03 contém o perfil completo.",
        },
        "F02": {
            "title": "Formatos coexistentes em contacto, data e identidade",
            "question": "Que formatos convivem nestes campos-chave?",
            "interpretation": "O telefone aparece em cinco formatos; a data mistura dd/mm, ISO, texto e serial Excel; o identificador mistura quatro tipos.",
            "n": "4 painéis",
            "denominator": "linhas de cada ficha",
            "source": "Responses e Follow-up; valores após classificação, sem alterar o original",
            "caveat": "As categorias descrevem o valor observado, não uma correção do dado.",
        },
        "F03": {
            "title": "Candidaturas por semana e estado",
            "question": "Como as candidaturas se distribuem no tempo?",
            "interpretation": "O volume cai ao longo da campanha; a última semana tem apenas três candidaturas e inclui o prazo.",
            "n": "24 candidaturas reais",
            "denominator": "candidaturas reais (exclui 2 linhas de teste)",
            "source": "Responses; campo Timestamp",
            "caveat": "A semana é uma convenção de calendário, não um lote operacional.",
        },
        "F04": {
            "title": "13 valores brutos para 8 estados canónicos",
            "question": "Quais variantes de estado existem e quanto pesam?",
            "interpretation": "Há 10 aprovações canónicas, mas a fórmula Summary conta 9; Lista B tem três variantes e só uma é apanhada pela fórmula.",
            "n": "26 linhas",
            "denominator": "26 linhas da ficha",
            "source": "Responses; campo Status",
            "caveat": "A cor agrupa significado; o rótulo y preserva a grafia original.",
        },
        "F05": {
            "title": "Cobertura por fonte e diferenças de estado",
            "question": "Que registos existem em cada fonte e onde há conflito?",
            "interpretation": "Há linhas só a montante (1009, 1018 e 1023, esta duplicada de 1016) e uma só a jusante (1012). Seis IDs sobrepostos têm estados diferentes: quatro progressões e duas reversões; só as reversões são contradições reais.",
            "n": "27 IDs (23 pessoas únicas)",
            "denominator": "IDs únicos entre Responses, Scoring e final",
            "source": "Responses, Scoring, final e Follow-up",
            "caveat": "A coluna Follow-up usa o melhor ID resolvido; Sam A. continua ambíguo e não é marcado.",
        },
        "F06": {
            "title": "O parser difere de dd/mm/yyyy em 10 registos",
            "question": "Onde a data de nascimento foi mal interpretada?",
            "interpretation": "Dez datas brutas diferem de dd/mm/yyyy. Para 1016, o duplicado 1023 confirma 1985-10-02, pelo que dob_clean está certo nesse caso; as outras nove continuam por auditar. Usar DOB como chave cega continua a produzir falsos negativos e positivos.",
            "n": "10 registos divergentes",
            "denominator": "26 registos de nascimento",
            "source": "Responses; Date of birth vs dob_clean",
            "caveat": "A regra dd/mm/yyyy é a declarada no formulário, não prova da data correta.",
        },
        "F07": {
            "title": "Que evidência liga o Follow-up a Adoptions?",
            "question": "Que evidência existe para ligar as duas equipas?",
            "interpretation": "O telefone é raro e não chega; o nome+inicial está disponível em 11 casos, mas raramente é único. A passagem determinística resolve 10 de 14 (um deles, Harry A., só por nome único, sem confirmação de estado); 1 fica ambíguo e 3 não têm candidato.",
            "n": "14 adopters do Follow-up",
            "denominator": "14 adopters únicos",
            "source": "Responses e Follow-up; telefone normalizado e nome abreviado",
            "caveat": "Animal específico é evidência fraca: nomes de animais repetem-se entre campanhas.",
        },
        "F08": {
            "title": "Candidatos de linkage e ambiguidade",
            "question": "Quem são os candidatos e onde a identidade é ambígua?",
            "interpretation": "Isla C. e Joe M. resolvem por telefone exato; Mark S. resolve para Mark Shaw (1016/1023), não Mark Singh; Claire H., Lucy F., Danielle H. e Hannah R. resolvem-se pela regra de estado/duplicação/pets. Sam A. fica ambíguo.",
            "n": "14 adopters do Follow-up",
            "denominator": "pares com score ≥25, top-3 por adopter",
            "source": "Responses e Follow-up; regras determinísticas de nome, telefone, estado e animal",
            "caveat": "O score é triagem; a resolução usa clusters de pessoa e estado, não só o score.",
        },
        "F09": {
            "title": "Scores de screening e desfecho por candidatura",
            "question": "Como Call, Visit e Fit se distribuem e se ligam ao desfecho?",
            "interpretation": "Scores altos aparecem em candidaturas aprovadas, mas também em waitlist e rejeitadas; o desfecho não é explicado por um único sinal.",
            "n": "16 candidaturas com scoring",
            "denominator": "24 candidaturas reais",
            "source": "Scoring + Responses + final",
            "caveat": "Amostra pequena e sem follow-up completo; não inferir causalidade. * Visit de 1020 foi extraído do texto original.",
        },
        "F10": {
            "title": "Cobertura do processo de adoção",
            "question": "Onde o funil perde registos?",
            "interpretation": "24 candidaturas reais (23 pessoas únicas), 16 com scoring, 13 em final e 11 aprovadas; o funil perde mais registos entre candidatura e scoring.",
            "n": "24 candidaturas; 23 pessoas",
            "denominator": "24 reais; 13 em final",
            "source": "Responses, Scoring e final",
            "caveat": "Comparação de cobertura, não uma taxa de conversão entre etapas.",
        },
        "F11": {
            "title": "O que o Follow-up observa",
            "question": "Que resultados e stages de follow-up existem?",
            "interpretation": "Só 'Handed over' tem follow-up 1m/6m; devoluções, não recolhas e reservas aparecem sem data de contacto. As 16 linhas são 15 episódios: DOG-0424 é fallback e DOG-0418 → DOG-0421 é uma troca, não duplicações.",
            "n": "16 linhas do Follow-up",
            "denominator": "15 episódios de placement (16 linhas menos a linha de troca)",
            "source": "04_team_b_followup_animals.csv",
            "caveat": "A lista parece corrente, não uma coorte fechada; o ano não está registado.",
        },
        "F12": {
            "title": "Prioridade das anomalias semânticas",
            "question": "Que anomalias têm maior impacto operacional?",
            "interpretation": "Identidade, diferenças de estado e datas sem ano dominam a prioridade; não são apenas 'células sujas', são falhas de modelo de dados. Depois da resolução determinística, a ambiguidade de linkage resume-se a Sam A. e aos 3 adopters sem candidato.",
            "n": "19 anomalias",
            "denominator": "top 12 de 19",
            "source": "Registo de anomalias da EDA (T14)",
            "caveat": "O score é uma heurística de priorização, não uma medida de risco.",
        },
    }

    def __init__(self, path: Path = REPORT_PATH):
        self.path = path

    def write(
        self,
        tables: dict[str, pd.DataFrame],
        figures: list[dict],
        manifest: dict,
    ) -> Path:
        kpis = tables["T17_kpis"].set_index("metric")["value"]
        issues = tables["T14_issue_register"]
        links = tables["T11_adopter_links"]
        summary = tables["T18_summary_reconciliation"]
        lines: list[str] = []
        lines.extend(
            [
                "# Hearthway Rehoming Network — EDA das adoções de primavera 2026",
                "",
                "**Pergunta central:** que sinais de triagem e que falhas de registo "
                "impedem saber quais adoções duraram e porquê?",
                "",
                "Este relatório acompanha o protótipo de registo partilhado entre a equipa "
                "de Adoptions e a equipa de Follow-up. O objetivo não é escolher um "
                "algoritmo, mas tornar visíveis os problemas de estrutura, identidade e "
                "estado que hoje limitam qualquer análise.",
                "",
                "## Resumo executivo",
                "",
                f"- **{int(kpis['real_applications'])} candidaturas reais** em Responses "
                f"({int(kpis['unique_people'])} pessoas únicas), além de "
                f"{int(kpis['test_rows'])} linhas de teste; 1006 não existe, 1012 só "
                "aparece em final e 1016/1023 são a mesma Mark Shaw.",
                f"- **{int(kpis['with_status'])} de {int(kpis['real_applications'])}** "
                "candidaturas reais têm estado preenchido; há 13 valores brutos de Status "
                "para 8 estados canónicos, incluindo desconhecido.",
                f"- **{int(kpis['status_conflicts'])} dos 12 IDs sobrepostos** têm estados "
                f"diferentes: {int(kpis['status_progressions'])} são progressões "
                f"(Waitlist/Reuse/Visit → Approved) e {int(kpis['status_reversals'])} são "
                "reversões (1022 e 1024, Approved → Waitlist). Só as reversões são "
                "contradições reais; as progressões são o ciclo de vida.",
                "- As fórmulas da sheet Summary **não são uma fonte fiável de KPIs**: 83 "
                "células estão sem cache, 5 têm erro e a fórmula Approved conta 9 em vez "
                "de 10 aprovações canónicas.",
                "- Os scores de screening não mostram separação limpa entre aprovados, "
                "waitlist e candidaturas sem `final`; 16 casos e estados sobrepostos não "
                "permitem estimar predictividade.",
                f"- **{int(kpis['followup_rows'])} linhas de Follow-up** representam "
                f"{int(kpis['followup_adopters'])} adopters, "
                f"{int(kpis['followup_animals'])} códigos de animal e "
                f"{int(kpis['followup_episodes'])} episódios de placement; "
                f"{int(kpis['followup_without_record'])} linhas não têm 1m/6m. "
                "DOG-0424 é a mesma Lola em fallback, não uma duplicação; "
                "DOG-0418 → DOG-0421 é uma troca.",
                f"- A ligação entre equipas é fraca no telefone (**{int(kpis['phone_exact'])} "
                "de 14 adopters**), mas uma passagem determinística resolve "
                f"**{int(kpis['linkage_resolved'])} de 14**: 2 por telefone exato e 8 por "
                "nome + estado, duplicação de pessoa ou animais do agregado; um destes "
                "(Harry A.) é só uma correspondência única de nome, sem confirmação de "
                "estado. "
                f"Fica {int(kpis['ambiguous'])} ambíguo (Sam A.) e "
                f"{int(kpis['no_candidate'])} sem candidato (Pam Q., Oscar S., Ivy C.).",
                f"- **DOB não é uma chave segura:** {int(kpis['dob_mismatch'])} datas "
                "brutas diferem de dd/mm/yyyy; 1016 é validado pelo duplicado 1023 "
                "(1985-10-02), mas as outras nove continuam por auditar.",
                "",
                "**Leitura principal:** o problema não é apenas “sujidade”. É a ausência "
                "de uma chave de pessoa estável, de um estado por equipa com timestamp e "
                "de uma coorte fechada de placements. Sem isso, os sinais de screening "
                "não podem ser avaliados de forma convincente. A inferência determinística "
                "resolve os casos em que os próprios ficheiros dão evidência suficiente; "
                "não substitui a revisão humana onde as fontes se contradizem.",
                "",
                "A resposta à pergunta 2 do case — os cinco itens mais importantes e o "
                "tratamento proposto — está na secção final.",
                "",
                "## Como reproduzir",
                "",
                "```bash",
                "uv run python -m data",
                "```",
                "",
                "A pipeline lê os ficheiros originais em modo read-only, reconstrói as "
                "tabelas derivadas em memória e escreve os artefactos em `outputs/`.",
                "",
                "## Âmbito e denominadores",
                "",
                "- `Responses` é a ficha de candidatura; as linhas 1000 e 1017 são testes "
                "e são excluídas dos KPIs.",
                "- `final` parece ser a lista operacional de placements, mas inclui 1012, "
                "ausente em Responses; não é uma coorte fechada.",
                "- `Follow-up` não tem IDs de candidatura nem ano nas datas. A ligação a "
                "Adoptions foi resolvida deterministicamente onde os ficheiros davam "
                "evidência suficiente; os casos restantes continuam a exigir confirmação.",
                "- Nenhuma conclusão é causal: a amostra é pequena e o follow-up é "
                "incompleto.",
                "",
                "## Linkage determinístico: o que os ficheiros já permitem decidir",
                "",
                "A revisão não trata todos os pares como igualmente ambíguos. Foram "
                "aplicadas regras que um analista pode reproduzir sem perguntar a ninguém:",
                "",
                "1. **Pessoa primeiro:** o mesmo número de adopter (ou nome + telefone + "
                "DOB) agrupa linhas. 1016 e 1023 são a mesma pessoa (Mark Shaw; adopter "
                "no. 060064440, telefone 07570 468615, DOB 1985-10-02).",
                "2. **Estado depois:** um candidato `Rejected` ou `List B` perde para um "
                "candidato aprovado/in final com o mesmo nome + inicial.",
                "3. **Pets só como desempate:** quando dois candidatos aprovados têm o "
                "mesmo nome + inicial, o tipo de animal do Follow-up pode desempatar "
                "(Hannah R. → 1005, que tem dois gatos; 1010 não tem gatos).",
                "4. **Sem decisão forçada:** se nenhum candidato é aprovado/in final, ou "
                "se o desempate não é determinístico, o caso fica marcado como ambíguo.",
                "",
                "| Follow-up | Leitura anterior | Resolução determinística | Evidência |",
                "| --- | --- | --- | --- |",
                "| Mark S. | 1011 Mark Singh (rejected) | **1016 Mark Shaw** | 1016/1023 são a mesma pessoa; 1016 está em final Approved. Mark Singh está Rejected. |",
                "| Claire H. | 1004/1019 Claire Harrison (empate) | **1004 Claire Harrison** | 1004 Approved/in final; 1019 Rejected. |",
                "| Lucy F. | 1001/1026 Lucy (empate) | **1001 Lucy Fisher** | 1001 Approved/in final; 1026 List B. |",
                "| Danielle H. | 1014/1015 Danielle (empate) | **1015 Danielle Hughes** | 1015 Approved/in final; 1014 List B. |",
                "| Hannah R. | 1005/1010 Hannah R. (empate) | **1005 Hannah Rowe** | Ambos aprovados/in final; só 1005 tem dois gatos, como o Follow-up. |",
                "| Sam A. | 1003 Sam Ahmed | **mantém-se ambíguo** | 1003 Rejected - previous return; 1027 sem estado. Nenhum é aprovado/in final; as evidências apontam em direções diferentes. |",
                "| Pam Q., Oscar S., Ivy C. | sem candidato | **sem candidato** | Não há nome/telefone correspondente; provavelmente outra coorte/centro ou registo em falta. |",
                "",
                "O resultado é uma redução de 6 casos ambíguos para 1, sem esconder os "
                "candidatos descartados: a tabela T11 mantém as alternativas e o motivo. "
                "A mesma lógica corrige a leitura da data: o valor de 1016 (1985-10-02) "
                "não é um erro de dados, é confirmado pela linha 1023 em formato ISO. As "
                "outras nove datas divergentes continuam a precisar de auditoria.",
                "",
            ]
        )
        lines.extend(self._figure_section("estrutural", "1. EDA estrutural", figures))
        lines.extend(self._figure_section("qualidade", "2. Qualidade dos dados", figures))
        lines.extend(self._figure_section("semantica", "3. EDA semântica", figures))

        lines.extend(
            [
                "## 4. Tabelas de referência",
                "",
                "Todas as tabelas estão em `outputs/tables/` e consolidadas em "
                "`outputs/tables/eda_tables.xlsx`.",
                "",
                "### KPIs e reconciliação",
                "",
                self._md_table(
                    tables["T17_kpis"],
                    [
                        "metric",
                        "value",
                        "unit",
                        "definition",
                    ],
                    25,
                ),
                "",
                self._md_table(
                    summary,
                    ["metric", "summary_formula", "recomputed", "difference", "note"],
                    12,
                ),
                "",
                "### Sinais de screening e desfecho",
                "",
                self._md_table(
                    tables["T26_screening_by_outcome"],
                    [
                        "final_group",
                        "applications",
                        "call_mean",
                        "visit_mean",
                        "fit_mean",
                        "score_mean",
                        "application_ids",
                    ],
                    10,
                ),
                "",
                "Os scores médios não separam de forma limpa aprovados, waitlist e "
                "candidaturas sem `final`. Com 16 casos e estados sobrepostos, isto é "
                "uma leitura descritiva, não um teste preditivo.",
                "",
                "### Linkage entre equipas",
                "",
                self._md_table(
                    links,
                    [
                        "adopter",
                        "best_id",
                        "best_name",
                        "best_status",
                        "best_final_status",
                        "confidence",
                        "ambiguity",
                        "resolution",
                        "same_person_ids",
                        "alternatives",
                    ],
                    20,
                ),
                "",
                "A coluna `resolution` mostra a regra que decidiu o par; `alternatives` "
                "preserva os candidatos descartados com o respetivo estado. Sam A. fica "
                "sem `best_id` de propósito: 1003 (Rejected) e 1027 (sem estado) não têm "
                "evidência suficiente para um merge automático.",
                "",
                "### Anomalias prioritárias",
                "",
                self._md_table(
                    issues.head(12),
                    [
                        "issue_id",
                        "category",
                        "issue",
                        "frequency",
                        "impact",
                        "priority_score",
                        "treatment",
                    ],
                    12,
                ),
                "",
                "A lista completa, com evidência e denominador, está em "
                "`T14_issue_register.csv`.",
                "",
                "## 5. Perguntas para as equipas",
                "",
                "1. **O que significa `Ref`?** É uma referência de revisão, um lote ou "
                "outra chave? Porque falta em quase todos os registos?",
                "2. **Quem atualiza `final` e quando?** É uma lista de placements, de "
                "aprovações ou de decisões de chamada?",
                "3. **O Follow-up é a coorte completa de placements** ou apenas os casos "
                "que a equipa estava a acompanhar nessa semana?",
                "4. **Que ano têm as datas `updated`?** Sem ano, não é possível calcular "
                "tempo até devolução ou follow-up.",
                "5. **1012 foi criado diretamente em final?** Que outros registos podem "
                "existir apenas numa das listas?",
                "6. **Há agregados familiares?** Dois adopters podem partilhar telefone, "
                "morada ou animal; o modelo atual não representa isso.",
                "7. **1016 e 1023 são a mesma pessoa ou duas candidaturas?** Os dados "
                "dizem que sim (adopter no., telefone e DOB); confirmar se foi correção "
                "ou re-submissão.",
                "8. **Sam A. é 1003, 1027 ou outra coorte?** 1003 é Rejected - previous "
                "return; 1027 não tem estado. As evidências não permitem decidir sem "
                "confirmação humana.",
                "9. **Quem valida os candidatos de linkage?** Mostrar evidência, score e "
                "alternativas; nunca fazer merge automático de identidades.",
                "10. **O que é “List B” e “Reuse”** no processo real? São estados, filas "
                "ou resultados?",
                "",
                "## 6. Implicações para o protótipo",
                "",
                "- Criar `person_id` e `household_id` estáveis; nomes, telefones e "
                "documentos passam a ser atributos, não chaves. O caso 1016/1023 mostra "
                "que uma pessoa pode ter mais de uma candidatura.",
                "- Guardar eventos por fonte (`application`, `screening`, `decision`, "
                "`placement`, `followup`) com timestamp e autor.",
                "- Separar estado de candidatura, estado de placement e estado de "
                "follow-up; não sobrescrever o estado da outra equipa.",
                "- Não calcular KPIs a partir de fórmulas da sheet; recalcular na "
                "pipeline e comparar com o valor apresentado.",
                "- Normalizar telefone para E.164, datas para ISO 8601 e listas de "
                "estado fechadas no formulário.",
                "- Tratar o linkage como triagem: aplicar primeiro regras determinísticas "
                "(adopter no., telefone, DOB, estado, pets do agregado) e só depois "
                "revisão humana. O Mark S. → Mark Shaw é resolúvel sem perguntar a "
                "ninguém; Sam A. não é.",
                "- Registar a coorte de Follow-up com `placement_id`, data de entrega, "
                "contacto e resultado; distinguir “sem follow-up” de “sem contacto” e "
                "não contar a linha intermédia de uma troca como placement.",
                "",
                "## 7. Limitações",
                "",
                "- As contagens de Follow-up são descritivas; não há denominador de "
                "placements elegíveis.",
                "- O linkage usa nome abreviado, telefone e animal; não valida morada, "
                "email nem documento. A resolução determinística cobre 10 de 14 "
                "adopters, mas Harry A. é só uma correspondência única de nome; Sam A. "
                "e os 3 sem candidato continuam sem confirmação.",
                "- A troca `DOG-0418 → DOG-0421` e a reutilização `DOG-0424` mostram que "
                "o animal também não é uma chave estável; são eventos operacionais, não "
                "duplicações.",
                "- O parser de datas foi auditado com a regra dd/mm/yyyy do formulário; "
                "1016 é confirmado pelo duplicado 1023, mas as outras nove datas "
                "divergentes continuam por auditar.",
                "- Não foi feita inferência estatística nem modelação preditiva; a "
                "amostra e a qualidade dos outcomes não o justificam.",
                "",
                "## 8. Ficheiros gerados",
                "",
                f"- Figuras: {len(figures)} PNG em `outputs/figures/`.",
                f"- Tabelas: {len(tables)} CSV em `outputs/tables/`.",
                "- Manifesto de figuras: `outputs/figure_manifest.csv`.",
                "- QA visual: `outputs/tables/figure_qa.csv`.",
                "- Manifesto de execução: `outputs/run_manifest.json`.",
                "",
                "### Tabelas",
                "",
            ]
        )
        for name, frame in tables.items():
            lines.append(
                f"- `{name}` — {len(frame)} linhas · `outputs/tables/{name}.csv`"
            )
        lines.extend(
            [
                "",
                "---",
                "",
                "## Case question 2 · What stands out, and what you would need to use this data reliably",
                "",
                "_Case question 2 — answer. The EDA above is the evidence; this is the "
                "filtered shortlist._",
                "",
                "I would not simply take the top five by anomaly score. The five below "
                "are the ones that decide whether a shared record can answer Hearthway's "
                "questions. Labels follow the requested convention: **fix at origin**, "
                "**fix in transit**, or **leave as is and agree on a seam**.",
                "",
                "The deterministic pass changes the starting point: 10 of 14 Follow-up "
                "adopters now resolve without a human (2 by exact phone, 8 by name + "
                "status, person duplicate or household pets; one of these is provisional "
                "on name alone), leaving 1 ambiguous "
                "(Sam A.) and 3 with no candidate. Mark S. is Mark Shaw (1016), not Mark "
                "Singh (1011); 1016 and 1023 are the same person. That is why the five "
                "items below are about missing keys and semantics, not about cell-level "
                "dirt.",
                "",
                "### 1. A person is not a key; one person can be several rows, and Follow-up only knows an abbreviated name",
                "",
                "**Label: fix at origin.**",
                "",
                "**What the files show.** 1016 and 1023 are the same Mark Shaw: same "
                "adopter no. 060064440, same phone 07570 468615, same DOB 1985-10-02. "
                "Follow-up's 'Mark S.' is that person, not Mark Singh (1011, Rejected). "
                "The same deterministic logic resolves Claire H. → 1004 (not 1019, "
                "Rejected), Lucy F. → 1001 (not 1026, List B), Danielle H. → 1015 (not "
                "1014, List B), and Hannah R. → 1005 (two cats, matching the two "
                "Follow-up cats; 1010 is the weaker alternative).",
                "",
                "**Plausible reason a competent person did it this way.** The form invites "
                "a second submission to correct a request, so a re-application becomes a "
                "new row; the sheet is a campaign log, not a person register. Follow-up "
                "staff write the name they use on the phone, and the adopter number is "
                "only entered by returning adopters.",
                "",
                "**Why it matters for Hearthway.** Without a person/household ID, the "
                "network cannot follow one adopter across applications, re-adoptions and "
                "returns, and entity errors directly contaminate any screening-to-outcome "
                "analysis.",
                "",
                "**Visible in the files, or ask?** Visible: adopter number, phone, DOB and "
                "names. Ask whether 1016/1023 was a correction or a genuine second "
                "application, and whether Follow-up includes prior cohorts — the 3 "
                "adopters with no candidate (Pam Q., Oscar S., Ivy C.) may be outside "
                "the spring base.",
                "",
                "### 2. Cross-team linkage has no shared key; phone is rare and names are ambiguous",
                "",
                "**Label: fix at origin** — add an immutable application/person ID to the "
                "Follow-up export. Keep a human-review seam for the residual.",
                "",
                "**What the files show.** Only 2 of 14 adopters have an exact phone. "
                "Name + initial gives 11 candidates, but several names repeat: two Claire "
                "Harrisons, two Hannah R., two Lucy F., two Danielle H., and two Mark "
                "S. people (Mark Singh and Mark Shaw, the latter with two rows). "
                "After the deterministic pass, 10 of 14 resolve (one, Harry A., only by "
                "unique name), 1 remains genuinely ambiguous (Sam A.: 1003 is 'Rejected "
                "- previous return', 1027 has a dog and no status; the evidence points "
                "in different directions), and 3 have no candidate.",
                "",
                "**Plausible reason.** Follow-up is a weekly operational list, updated "
                "after calls; staff identify people by the name they know, and phones "
                "differ between teams or are shared/placeholder. It was never designed as "
                "an integration feed.",
                "",
                "**Why it matters.** A false merge is worse than no merge: it would attach "
                "a return or a 6-month outcome to the wrong person and bias the very "
                "signal analysis the network wants.",
                "",
                "**Visible in the files, or ask?** Visible. Ask for the Follow-up cohort "
                "definition and whether 'no candidate' means another centre/cohort or a "
                "missing record.",
                "",
                "### 3. One 'Status' field mixes application decision, process stage and placement outcome",
                "",
                "**Label: leave as is and agree on a seam** — keep each team's vocabulary, "
                "but map it explicitly; do not collapse it into one mutable status.",
                "",
                "**What the files show.** 'Approved' in the Adoptions sheet does not mean "
                "handed over — Rachel's quote: 'Their sheet still says Approved for people "
                "who never came to pick the animal up.' The 6 raw status differences "
                "between Responses and final are not all errors: 4 are forward movement "
                "(Waitlist/Reuse/Visit → Approved) and 2 are reversals (1022, 1024: "
                "Approved → Waitlist). Mark Shaw's 1016 'Visit' is also resolved by the "
                "duplicate 1023 'Approved'. 'Home visit' in Summary is a formula counting "
                "the status 'visit' (1), while there are 16 scored visits.",
                "",
                "**Plausible reason.** Each team uses status for its own decision. "
                "Adoptions records a screening decision; Follow-up records a placement "
                "event. They report to the same coordinator but keep different tools, and "
                "the spreadsheet was copied across campaigns.",
                "",
                "**Why it matters.** Without a seam, the funnel treats 'approved' as "
                "'placed', and the funder question 'how many are still in place?' cannot "
                "be answered. It also makes the screening-to-outcome analysis compare the "
                "wrong endpoints.",
                "",
                "**Visible in the files, or ask?** Visible in the files and the quotes. Ask "
                "what 'visit', 'Reuse' and 'List B' mean operationally, and which team owns "
                "each transition.",
                "",
                "### 4. Follow-up is a current weekly list, not a closed placement cohort",
                "",
                "**Label: fix at origin** — define the cohort, add `placement_id`, full "
                "dates and a contact result per contact.",
                "",
                "**What the files show.** 16 rows represent 14 adopters, 15 animal codes "
                "and 15 placement episodes, not 16 placements. Joe M.'s two rows are one "
                "swap (DOG-0418 → DOG-0421); DOG-0424 is the same Lola offered to Danielle "
                "H. (not collected) and then to Harry A. (waitlist) — a fallback "
                "reservation, not a duplicate. Nine of 16 rows have no 1m/6m follow-up, "
                "and every 'updated' date is day-month only (Jul–Dec), so time-to-return "
                "cannot be computed.",
                "",
                "**Plausible reason.** Follow-up staff update the list every week and "
                "track the current animal/status, not an auditable placement history; the "
                "year is obvious to them at the time, and swaps/fallbacks are operational "
                "notes.",
                "",
                "**Why it matters.** 'How many of last year's adoptions are still in "
                "place?' needs a denominator and a clock. A current list cannot provide "
                "either, and counting rows as placements overstates the cohort.",
                "",
                "**Visible in the files, or ask?** Visible in the notes. Ask whether the 16 "
                "rows are the complete spring cohort or only the cases being watched that "
                "week, and which year the dates belong to (2025 vs 2026 changes the "
                "interpretation).",
                "",
                "### 5. The spreadsheet's formula layer is not a reliable KPI source",
                "",
                "**Label: fix in transit** — recompute in the pipeline; do not read formula "
                "results.",
                "",
                "**What the files show.** 83 formula cells have no cached value and 5 "
                "cells are errors (#REF!/#ERROR!). Summary says 26 total requests (24 "
                "real), 9 approved (10 canonical), 1 List B (3), 1 home visit (16 scored "
                "visits), and its components sum to 20, not 24. The errors come from "
                "positional VLOOKUPs and rows inserted/deleted between campaigns.",
                "",
                "**Plausible reason.** A working sheet copied and adapted over several "
                "campaigns, opened outside Excel so formulas are not recalculated; the "
                "'Home visit' formula is inherited and counts the wrong thing.",
                "",
                "**Why it matters.** Funder reporting and any dashboard built on those "
                "cells would be wrong and not reproducible. Recomputing in the pipeline "
                "makes the numbers auditable and lets the source stay read-only.",
                "",
                "**Visible in the files, or ask?** Visible (T06/T18); no need to ask, "
                "except to confirm the intended definition of 'Approved' and 'Home "
                "visit'.",
                "",
            ]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")
        return self.path

    def _figure_section(
        self, stage: str, heading: str, figures: list[dict]
    ) -> list[str]:
        stage_figures = [row for row in figures if row["stage"] == stage]
        lines = [f"## {heading}", ""]
        for row in stage_figures:
            lines.extend(self._figure_block(row))
        return lines

    def _figure_block(self, row: dict) -> list[str]:
        text = self.FIGURE_TEXT.get(row["figure_id"], {})
        title = text.get("title", row["title"])
        question = text.get("question", row["question"])
        interpretation = text.get("interpretation", row["interpretation"])
        n = text.get("n", row["n"])
        denominator = text.get("denominator", row["denominator"])
        source = text.get("source", row["source"])
        caveat = text.get("caveat", row.get("caveat", ""))
        lines = [
            f"### {row['figure_id']} — {title}",
            "",
            f"![{row['figure_id']} — {title}]({row['path']})",
            "",
            f"**Pergunta:** {question}",
            "",
            f"**Leitura:** {interpretation}",
            "",
            f"**n / denominador:** {n} / {denominator}.",
            "",
            f"**Fonte:** {source}.",
            "",
        ]
        if caveat:
            lines.extend([f"**Ressalva:** {caveat}", ""])
        if row.get("qa_status") != "pass":
            lines.extend(
                [
                    f"**QA visual:** {row.get('qa_status')} — "
                    f"{row.get('qa_warnings', '')}",
                    "",
                ]
            )
        return lines

    @staticmethod
    def _md_table(
        frame: pd.DataFrame,
        columns: list[str],
        max_rows: int,
    ) -> str:
        if frame.empty:
            return "_Sem registos._"
        selected = frame[[column for column in columns if column in frame.columns]]
        selected = selected.head(max_rows)
        headers = [str(column) for column in selected.columns]
        rows = []
        for _, row in selected.iterrows():
            values = []
            for value in row:
                if pd.isna(value):
                    text = ""
                elif isinstance(value, float):
                    text = f"{value:.2f}".rstrip("0").rstrip(".")
                else:
                    text = str(value)
                values.append(text.replace("|", "\\|").replace("\n", " "))
            rows.append("| " + " | ".join(values) + " |")
        header = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        return "\n".join([header, separator] + rows)
