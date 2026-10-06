# Detector battery (dev) — label review sheet

271 rows over 66 premises. Each row: the sentence, the label (class → expected verdict), and the excerpt of the provision it was judged against. Mark any label you disagree with by row id.

| Class | Rows | Expected |
|---|---:|---|
| connective | 10 | EMIT |
| dropped_qualifier | 9 | ROLLBACK |
| grounded_paraphrase | 125 | EMIT |
| modal_shift | 17 | ROLLBACK |
| premise_correction | 6 | EMIT |
| unsupported_plausible | 33 | ROLLBACK |
| value_swap | 8 | ROLLBACK |
| version_swap | 8 | ROLLBACK |
| wrong_citation | 15 | ROLLBACK |
| wrong_figure | 24 | ROLLBACK |
| wrong_instrument | 16 | ROLLBACK |

## uk/ukpga/1996/18/s23

Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0001** · `grounded_paraphrase` → **EMIT**  
  Sentence: A worker can complain to an employment tribunal that their employer made a deduction from their wages in breach of section 13.  
  Source ([s23/1](https://www.legislation.gov.uk/ukpga/1996/18/section/23/1)): “A worker may present a complaint to an employment tribunal— (a) that his employer has made a deduction from his wages in contravention of section 13”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0002** · `grounded_paraphrase` → **EMIT**  
  Sentence: The complaint generally has to be presented within three months starting with the date the wages were paid.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “unless it is presented before the end of the period of three months beginning with”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0003** · `grounded_paraphrase` → **EMIT**  
  Sentence: Where there was a series of deductions, time runs from the last deduction in the series.  
  Source ([s23/3](https://www.legislation.gov.uk/ukpga/1996/18/section/23/3)): “are to the last deduction or payment in the series”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0004** · `wrong_figure` → **ROLLBACK**  
  Sentence: A wages complaint must be presented within six months of the date of payment.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “before the end of the period of three months”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0005** · `wrong_figure` → **ROLLBACK**  
  Sentence: A tribunal cannot look at deductions from wages paid more than three years before the complaint was presented.  
  Source ([s23/4A](https://www.legislation.gov.uk/ukpga/1996/18/section/23/4A)): “before the period of two years ending with the date of presentation of the complaint”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0006** · `modal_shift` → **ROLLBACK**  
  Sentence: If it was not reasonably practicable to claim in time, the tribunal must hear the complaint as long as it is presented within a reasonable further period.  
  Source ([s23/4](https://www.legislation.gov.uk/ukpga/1996/18/section/23/4)): “the tribunal may consider the complaint if it is presented within such further period as the tribunal considers reasonable”
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0007** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: A tribunal will never hear a deduction claim presented more than three months after the wages were paid.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “Subject to subsection (4), an employment tribunal shall not consider a complaint”  
  Note: Drops 'Subject to subsection (4)' (the not-reasonably-practicable extension).
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0008** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Before presenting the complaint, the worker must first raise a written grievance with the employer.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “an employment tribunal shall not consider a complaint under this section unless it is presented before the end of the period of three months”  
  Note: No grievance requirement in the premise.
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0009** · `wrong_citation` → **ROLLBACK**  
  Sentence: Section 23(2) of the Employment Rights Act 1996 lets the tribunal extend the time limit where it was not reasonably practicable to claim in time.  
  Source ([s23/4](https://www.legislation.gov.uk/ukpga/1996/18/section/23/4)): “Where the employment tribunal is satisfied that it was not reasonably practicable”  
  Note: Misattributed: the extension is s.23(4); s.23(2) exists, so the cite itself is real.
Query (legal-rag-router uk-concept-0003): `wages deduction complaint employment tribunal time limit three months`
- **vdev-0010** · `connective` → **EMIT**  
  Sentence: There are two parts to the answer.  
  Source ([s23/1](https://www.legislation.gov.uk/ukpga/1996/18/section/23/1)): “A worker may present a complaint to an employment tribunal”

## uk/ukpga/1996/18/s119

Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0011** · `grounded_paraphrase` → **EMIT**  
  Sentence: For each year of employment in which the employee was aged 41 or over, the basic award allows one and a half weeks' pay.  
  Source ([s119/2](https://www.legislation.gov.uk/ukpga/1996/18/section/119/2)): “one and a half weeks’ pay for a year of employment in which the employee was not below the age of forty-one”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0012** · `grounded_paraphrase` → **EMIT**  
  Sentence: Years worked between the ages of 22 and 40 count at one week's pay each.  
  Source ([s119/2](https://www.legislation.gov.uk/ukpga/1996/18/section/119/2)): “one week’s pay for a year of employment (not within paragraph (a)) in which he was not below the age of twenty-two”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0013** · `grounded_paraphrase` → **EMIT**  
  Sentence: Only the most recent twenty years of employment are counted.  
  Source ([s119/3](https://www.legislation.gov.uk/ukpga/1996/18/section/119/3)): “no account shall be taken under that subsection of any year of employment earlier than those twenty years”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0014** · `value_swap` → **ROLLBACK**  
  Sentence: Each year worked at age 41 or above earns one week's pay.  
  Source ([s119/2](https://www.legislation.gov.uk/ukpga/1996/18/section/119/2)): “one and a half weeks’ pay for a year of employment in which the employee was not below the age of forty-one”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0015** · `value_swap` → **ROLLBACK**  
  Sentence: Years of employment before age 22 each count at one week's pay.  
  Source ([s119/2](https://www.legislation.gov.uk/ukpga/1996/18/section/119/2)): “half a week’s pay for a year of employment not within paragraph (a) or (b)”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0016** · `wrong_figure` → **ROLLBACK**  
  Sentence: Reckonable service is capped at the most recent 25 years.  
  Source ([s119/3](https://www.legislation.gov.uk/ukpga/1996/18/section/119/3)): “Where twenty years of employment have been reckoned”
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0017** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The basic award is reduced by any redundancy payment the employee has already received.  
  Source ([s119/1](https://www.legislation.gov.uk/ukpga/1996/18/section/119/1)): “Subject to the provisions of this section, sections 120 to 122 and section 126”  
  Note: True in law (s.122(4)) but not in this premise: the premise only cross-refers to s.122.
Query (legal-rag-router uk-concept-0010): `unfair dismissal basic award calculation age years service week's pay`
- **vdev-0018** · `wrong_citation` → **ROLLBACK**  
  Sentence: Under section 119(4), years before the age of 22 count at half a week's pay.  
  Source ([s119/2](https://www.legislation.gov.uk/ukpga/1996/18/section/119/2)): “half a week’s pay for a year of employment not within paragraph (a) or (b)”  
  Note: s.119 has no subsection (4); the rule is s.119(2)(c).

## uk/ukpga/1996/18/s1

Query (legal-rag-router uk-concept-0001): `employee written statement employment particulars start date pay hours`
- **vdev-0019** · `grounded_paraphrase` → **EMIT**  
  Sentence: An employer has to give a worker a written statement of the particulars of their employment.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1996/18/section/1/1)): “the employer shall give to the worker a written statement of particulars of employment”
Query (legal-rag-router uk-concept-0001): `employee written statement employment particulars start date pay hours`
- **vdev-0020** · `grounded_paraphrase` → **EMIT**  
  Sentence: The statement must be given no later than the day the employment begins.  
  Source ([s1/2](https://www.legislation.gov.uk/ukpga/1996/18/section/1/2)): “the statement must be given not later than the beginning of the employment”
Query (legal-rag-router uk-concept-0001): `employee written statement employment particulars start date pay hours`
- **vdev-0021** · `grounded_paraphrase` → **EMIT**  
  Sentence: It has to name the employer and the worker and give the date the employment began.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1996/18/section/1/3)): “(a) the names of the employer and worker, (b) the date when the employment began”
Query (legal-rag-router uk-concept-0001): `employee written statement employment particulars start date pay hours`
- **vdev-0022** · `modal_shift` → **ROLLBACK**  
  Sentence: The employer may provide a written statement of particulars if the worker asks for one.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1996/18/section/1/1)): “the employer shall give to the worker a written statement of particulars of employment”
Query (legal-rag-router uk-concept-0001): `employee written statement employment particulars start date pay hours`
- **vdev-0023** · `wrong_figure` → **ROLLBACK**  
  Sentence: Pay and hours must be stated as at a date no more than fourteen days before the statement is given.  
  Source ([s1/4](https://www.legislation.gov.uk/ukpga/1996/18/section/1/4)): “as at a specified date not more than seven days before the statement”

## uk/ukpga/1996/18/s50

Query (legal-rag-router uk-concept-0015): `time off work magistrate jury public duties employee`
- **vdev-0024** · `grounded_paraphrase` → **EMIT**  
  Sentence: An employer must let an employee who is a magistrate take time off during working hours to perform the duties of that office.  
  Source ([s50/1](https://www.legislation.gov.uk/ukpga/1996/18/section/50/1)): “An employer shall permit an employee of his who is— (a) a justice of the peace”  
  Note: Paraphrase: 'magistrate' for 'justice of the peace'.
Query (legal-rag-router uk-concept-0015): `time off work magistrate jury public duties employee`
- **vdev-0025** · `grounded_paraphrase` → **EMIT**  
  Sentence: The amount of time off is whatever is reasonable in all the circumstances.  
  Source ([s50/4](https://www.legislation.gov.uk/ukpga/1996/18/section/50/4)): “are those that are reasonable in all the circumstances”
Query (legal-rag-router uk-concept-0015): `time off work magistrate jury public duties employee`
- **vdev-0026** · `modal_shift` → **ROLLBACK**  
  Sentence: An employer may refuse a justice of the peace time off for their duties when the business is busy.  
  Source ([s50/1](https://www.legislation.gov.uk/ukpga/1996/18/section/50/1)): “An employer shall permit an employee of his who is— (a) a justice of the peace”
Query (legal-rag-router uk-concept-0015): `time off work magistrate jury public duties employee`
- **vdev-0027** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The employer must pay the employee their normal wages for time off taken for public duties.  
  Source ([s50/1](https://www.legislation.gov.uk/ukpga/1996/18/section/50/1)): “to take time off during the employee’s working hours”  
  Note: s.50 gives a right to time off, not to pay for it.
Query (legal-rag-router uk-concept-0015): `time off work magistrate jury public duties employee`
- **vdev-0028** · `connective` → **EMIT**  
  Sentence: Here is how the rules work.  
  Source ([s50/1](https://www.legislation.gov.uk/ukpga/1996/18/section/50/1)): “to take time off during the employee’s working hours”

## uk/ukpga/1992/52/s188

Query (legal-rag-router uk-informal-0009): `tulrca s.188`
- **vdev-0029** · `grounded_paraphrase` → **EMIT**  
  Sentence: Where 100 or more redundancies are proposed, consultation has to start at least 45 days before the first dismissal takes effect.  
  Source ([s188/1A](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1A)): “where the employer is proposing to dismiss 100 or more employees as mentioned in subsection (1) (A1), at least 45 days”
Query (legal-rag-router uk-concept-0020): `collective redundancies consult representatives 20 or more employees`
- **vdev-0030** · `grounded_paraphrase` → **EMIT**  
  Sentence: For 20 to 99 proposed redundancies, consultation must begin at least 30 days before the first dismissal.  
  Source ([s188/1A](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1A)): “(b) otherwise, at least 30 days, before the first of the dismissals takes effect”
Query (legal-rag-router uk-concept-0020): `collective redundancies consult representatives 20 or more employees`
- **vdev-0031** · `grounded_paraphrase` → **EMIT**  
  Sentence: The employer has to consult the appropriate representatives of the employees who may be affected.  
  Source ([s188/1](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1)): “The employer shall consult about the dismissals all the persons who are appropriate representatives of any of the employees who may be affected”
Query (legal-rag-router uk-informal-0009): `tulrca s.188`
- **vdev-0032** · `value_swap` → **ROLLBACK**  
  Sentence: Where 100 or more employees are to be dismissed, consultation must begin at least 30 days beforehand.  
  Source ([s188/1A](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1A)): “at least 45 days, and (b) otherwise, at least 30 days”
Query (legal-rag-router uk-concept-0020): `collective redundancies consult representatives 20 or more employees`
- **vdev-0033** · `wrong_figure` → **ROLLBACK**  
  Sentence: The duty applies where 20 or more employees at one establishment are to be dismissed within 60 days.  
  Source ([s188/1](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1)): “within a period of 90 days or less”
Query (legal-rag-router uk-concept-0020): `collective redundancies consult representatives 20 or more employees`
- **vdev-0034** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: Consultation must begin 45 days before the first dismissal takes effect.  
  Source ([s188/1A](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1A)): “at least 45 days”  
  Note: Drops 'at least' and the 100-or-more condition.
Query (legal-rag-router uk-concept-0020): `collective redundancies consult representatives 20 or more employees`
- **vdev-0035** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The employer must also write to every affected employee individually before consultation begins.  
  Source ([s188/1](https://www.legislation.gov.uk/ukpga/1992/52/section/188/1)): “The employer shall consult about the dismissals all the persons who are appropriate representatives”

## uk/ukpga/2010/15/s136

Query (legal-rag-router uk-concept-0032): `burden of proof discrimination claim shifts respondent explanation`
- **vdev-0036** · `grounded_paraphrase` → **EMIT**  
  Sentence: If there are facts from which the tribunal could decide that discrimination occurred, it must find a contravention unless the respondent shows it did not contravene the provision.  
  Source ([s136/2](https://www.legislation.gov.uk/ukpga/2010/15/section/136/2)): “the court must hold that the contravention occurred”  
  Note: Spans s.136(2), (3) and (6) (court includes an employment tribunal).
Query (legal-rag-router uk-concept-0032): `burden of proof discrimination claim shifts respondent explanation`
- **vdev-0037** · `grounded_paraphrase` → **EMIT**  
  Sentence: The burden of proof rule does not apply to proceedings for an offence under the Act.  
  Source ([s136/5](https://www.legislation.gov.uk/ukpga/2010/15/section/136/5)): “This section does not apply to proceedings for an offence under this Act.”
Query (legal-rag-router uk-concept-0032): `burden of proof discrimination claim shifts respondent explanation`
- **vdev-0038** · `modal_shift` → **ROLLBACK**  
  Sentence: Where such facts exist, the court may hold that the contravention occurred.  
  Source ([s136/2](https://www.legislation.gov.uk/ukpga/2010/15/section/136/2)): “the court must hold that the contravention occurred”
Query (legal-rag-router uk-concept-0032): `burden of proof discrimination claim shifts respondent explanation`
- **vdev-0039** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The claimant must prove discrimination beyond reasonable doubt.  
  Source ([s136/2](https://www.legislation.gov.uk/ukpga/2010/15/section/136/2)): “If there are facts from which the court could decide, in the absence of any other explanation”
Query (legal-rag-router uk-concept-0032): `burden of proof discrimination claim shifts respondent explanation`
- **vdev-0040** · `wrong_citation` → **ROLLBACK**  
  Sentence: Under section 163 of the Equality Act 2010, the burden shifts to the respondent once the claimant shows facts from which discrimination could be inferred.  
  Source ([s136/2](https://www.legislation.gov.uk/ukpga/2010/15/section/136/2)): “If there are facts from which the court could decide”

## uk/ukpga/2010/15/s109

Query (legal-rag-router uk-concept-0038): `employer liable for employee's discrimination all reasonable steps defence`
- **vdev-0041** · `grounded_paraphrase` → **EMIT**  
  Sentence: Anything an employee does in the course of employment is treated as also done by the employer, whether or not the employer knew or approved.  
  Source ([s109/1](https://www.legislation.gov.uk/ukpga/2010/15/section/109/1)): “Anything done by a person (A) in the course of A's employment must be treated as also done by the employer.”
Query (legal-rag-router uk-concept-0038): `employer liable for employee's discrimination all reasonable steps defence`
- **vdev-0042** · `grounded_paraphrase` → **EMIT**  
  Sentence: The employer has a defence if it shows it took all reasonable steps to prevent the employee from doing that thing.  
  Source ([s109/4](https://www.legislation.gov.uk/ukpga/2010/15/section/109/4)): “it is a defence for B to show that B took all reasonable steps to prevent A”
Query (legal-rag-router uk-concept-0038): `employer liable for employee's discrimination all reasonable steps defence`
- **vdev-0043** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: An employer is liable for anything its employees do.  
  Source ([s109/1](https://www.legislation.gov.uk/ukpga/2010/15/section/109/1)): “in the course of A's employment”  
  Note: Drops 'in the course of employment' and the reasonable-steps defence.
Query (legal-rag-router uk-concept-0038): `employer liable for employee's discrimination all reasonable steps defence`
- **vdev-0044** · `wrong_citation` → **ROLLBACK**  
  Sentence: The reasonable steps defence is in section 109(6).  
  Source ([s109/4](https://www.legislation.gov.uk/ukpga/2010/15/section/109/4)): “it is a defence for B to show that B took all reasonable steps”

## uk/ukpga/2010/15/s20 + uk/ukpga/2010/15/s21

Query (legal-rag-router uk-concept-0025): `employer failed adjust workplace substantial disadvantage disabled worker claim`
- **vdev-0045** · `grounded_paraphrase` → **EMIT**  
  Sentence: The duty to make reasonable adjustments is made up of three requirements.  
  Source ([s20/2](https://www.legislation.gov.uk/ukpga/2010/15/section/20/2)): “The duty comprises the following three requirements.”
Query (legal-rag-router uk-concept-0025): `employer failed adjust workplace substantial disadvantage disabled worker claim`
- **vdev-0046** · `grounded_paraphrase` → **EMIT**  
  Sentence: Failing to comply with the duty to make reasonable adjustments is discrimination against the disabled person.  
  Source ([s21/2](https://www.legislation.gov.uk/ukpga/2010/15/section/21/2)): “A discriminates against a disabled person if A fails to comply with that duty in relation to that person.”
Query (legal-rag-router uk-concept-0025): `employer failed adjust workplace substantial disadvantage disabled worker claim`
- **vdev-0047** · `grounded_paraphrase` → **EMIT**  
  Sentence: A disabled person cannot be made to pay towards the employer's costs of making the adjustments.  
  Source ([s20/7](https://www.legislation.gov.uk/ukpga/2010/15/section/20/7)): “is not (subject to express provision to the contrary) entitled to require a disabled person”
Query (legal-rag-router uk-concept-0025): `employer failed adjust workplace substantial disadvantage disabled worker claim`
- **vdev-0048** · `modal_shift` → **ROLLBACK**  
  Sentence: An employer may ask the disabled person to contribute to the cost of the adjustments.  
  Source ([s20/7](https://www.legislation.gov.uk/ukpga/2010/15/section/20/7)): “is not (subject to express provision to the contrary) entitled to require a disabled person”
Query (legal-rag-router uk-concept-0025): `employer failed adjust workplace substantial disadvantage disabled worker claim`
- **vdev-0049** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Employers with fewer than 15 employees are exempt from the duty to make reasonable adjustments.  
  Source ([s20/1](https://www.legislation.gov.uk/ukpga/2010/15/section/20/1)): “Where this Act imposes a duty to make reasonable adjustments on a person”

## uk/ukpga/1968/60/s9

Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0050** · `grounded_paraphrase` → **EMIT**  
  Sentence: Burglary of a dwelling carries a maximum of fourteen years' imprisonment on conviction on indictment.  
  Source ([s9/3](https://www.legislation.gov.uk/ukpga/1968/60/section/9/3)): “where the offence was committed in respect of a building or part of a building which is a dwelling, fourteen years”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0051** · `grounded_paraphrase` → **EMIT**  
  Sentence: A person commits burglary if they enter a building as a trespasser intending to steal anything in it.  
  Source ([s9/1](https://www.legislation.gov.uk/ukpga/1968/60/section/9/1)): “he enters any building or part of a building as a trespasser and with intent to commit any such offence”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0052** · `grounded_paraphrase` → **EMIT**  
  Sentence: The rules for dwellings also cover an inhabited vehicle or vessel, even while the occupant is away.  
  Source ([s9/4](https://www.legislation.gov.uk/ukpga/1968/60/section/9/4)): “shall apply also to an inhabited vehicle or vessel”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0053** · `value_swap` → **ROLLBACK**  
  Sentence: Burglary of someone's home is punishable by up to ten years' imprisonment.  
  Source ([s9/3](https://www.legislation.gov.uk/ukpga/1968/60/section/9/3)): “is a dwelling, fourteen years; (b) in any other case, ten years”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0054** · `wrong_figure` → **ROLLBACK**  
  Sentence: Burglary of non-residential premises carries a maximum of seven years' imprisonment.  
  Source ([s9/3](https://www.legislation.gov.uk/ukpga/1968/60/section/9/3)): “(b) in any other case, ten years”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0055** · `wrong_citation` → **ROLLBACK**  
  Sentence: The maximum penalties for burglary are set out in section 9(5) of the Theft Act 1968.  
  Source ([s9/3](https://www.legislation.gov.uk/ukpga/1968/60/section/9/3)): “A person guilty of burglary shall on conviction on indictment be liable”
Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0056** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: Burglary carries fourteen years' imprisonment.  
  Source ([s9/3](https://www.legislation.gov.uk/ukpga/1968/60/section/9/3)): “imprisonment for a term not exceeding— (a) where the offence was committed in respect of a building or part of a building which is a dwelling, fourteen years”  
  Note: Drops 'not exceeding' (a maximum) and the dwelling condition.

## uk/ukpga/1968/60/s22

Query (legal-rag-router uk-concept-0041): `dishonestly receiving stolen goods handling offence`
- **vdev-0057** · `grounded_paraphrase` → **EMIT**  
  Sentence: Handling stolen goods carries up to fourteen years' imprisonment on conviction on indictment.  
  Source ([s22/2](https://www.legislation.gov.uk/ukpga/1968/60/section/22/2)): “imprisonment for a term not exceeding fourteen years”
Query (legal-rag-router uk-concept-0041): `dishonestly receiving stolen goods handling offence`
- **vdev-0058** · `grounded_paraphrase` → **EMIT**  
  Sentence: A person handles stolen goods if, knowing or believing them to be stolen, they dishonestly receive them.  
  Source ([s22/1](https://www.legislation.gov.uk/ukpga/1968/60/section/22/1)): “knowing or believing them to be stolen goods he dishonestly receives the goods”
Query (legal-rag-router uk-concept-0041): `dishonestly receiving stolen goods handling offence`
- **vdev-0059** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Handling stolen goods is an offence under section 22 of the Fraud Act 2006.  
  Source ([s22/1](https://www.legislation.gov.uk/ukpga/1968/60/section/22/1)): “A person handles stolen goods if”
Query (legal-rag-router uk-concept-0041): `dishonestly receiving stolen goods handling offence`
- **vdev-0060** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The offence is only committed if the defendant knew for certain that the goods were stolen.  
  Source ([s22/1](https://www.legislation.gov.uk/ukpga/1968/60/section/22/1)): “knowing or believing them to be stolen goods”  
  Note: Belief suffices; the sentence narrows the mental element.

## uk/ukpga/2010/23/s7

Query (legal-rag-router uk-concept-0045): `company failed prevent bribery associated person adequate procedures defence`
- **vdev-0061** · `grounded_paraphrase` → **EMIT**  
  Sentence: A commercial organisation commits an offence if a person associated with it bribes another person to obtain or retain business for it.  
  Source ([s7/1](https://www.legislation.gov.uk/ukpga/2010/23/section/7/1)): “if a person (“A”) associated with C bribes another person intending— (a) to obtain or retain business for C”
Query (legal-rag-router uk-concept-0045): `company failed prevent bribery associated person adequate procedures defence`
- **vdev-0062** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is a defence for the organisation to prove that it had adequate procedures in place to prevent such conduct.  
  Source ([s7/2](https://www.legislation.gov.uk/ukpga/2010/23/section/7/2)): “it is a defence for C to prove that C had in place adequate procedures”
Query (legal-rag-router uk-concept-0045): `company failed prevent bribery associated person adequate procedures defence`
- **vdev-0063** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Under section 7 of the Bribery Act 2006, a company can be liable for failing to prevent bribery.  
  Source ([s7/1](https://www.legislation.gov.uk/ukpga/2010/23/section/7/1)): “A relevant commercial organisation (“C”) is guilty of an offence under this section”
Query (legal-rag-router uk-concept-0045): `company failed prevent bribery associated person adequate procedures defence`
- **vdev-0064** · `wrong_citation` → **ROLLBACK**  
  Sentence: The adequate procedures defence appears in section 7(4) of the Bribery Act 2010.  
  Source ([s7/2](https://www.legislation.gov.uk/ukpga/2010/23/section/7/2)): “it is a defence for C to prove that C had in place adequate procedures”  
  Note: Misattributed: the defence is s.7(2); s.7(4) exists (cross-references).
Query (legal-rag-router uk-concept-0045): `company failed prevent bribery associated person adequate procedures defence`
- **vdev-0065** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The offence only applies to companies incorporated in the United Kingdom.  
  Source ([s7/5](https://www.legislation.gov.uk/ukpga/2010/23/section/7/5)): “any other body corporate (wherever incorporated) which carries on a business, or part of a business, in any part of the United Kingdom”

## uk/ukpga/Vict/24-25/100/s20

Query (legal-rag-router uk-concept-0047): `wounding inflicting grievous bodily harm without intent`
- **vdev-0066** · `grounded_paraphrase` → **EMIT**  
  Sentence: Under section 20 of the Offences against the Person Act 1861, it is an offence to unlawfully and maliciously wound or inflict grievous bodily harm on another person, with or without a weapon.  
  Source ([100/s20](https://www.legislation.gov.uk/ukpga/Vict/24-25/100/section/20)): “Whosoever shall unlawfully and maliciously wound or inflict any grievous bodily harm upon any other person, either with or without any weapon or instrument”
Query (legal-rag-router uk-concept-0047): `wounding inflicting grievous bodily harm without intent`
- **vdev-0067** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The maximum sentence for an offence under section 20 is five years' imprisonment.  
  Source ([100/s20](https://www.legislation.gov.uk/ukpga/Vict/24-25/100/section/20)): “shall be liable to be kept in penal servitude”  
  Note: True in law, but the penalty text in the premise is repealed (dot run); not in the premise.
Query (legal-rag-router uk-concept-0047): `wounding inflicting grievous bodily harm without intent`
- **vdev-0068** · `wrong_citation` → **ROLLBACK**  
  Sentence: Section 18 of the 1861 Act makes it an offence to wound another person without intent.  
  Source ([100/s20](https://www.legislation.gov.uk/ukpga/Vict/24-25/100/section/20)): “Whosoever shall unlawfully and maliciously wound”

## uk/ukpga/1971/48/s1

Query (legal-rag-router uk-concept-0048): `destroying damaging property belonging to another without lawful excuse`
- **vdev-0069** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is an offence to destroy or damage property belonging to another without lawful excuse, intending to do so or being reckless as to whether it would be destroyed or damaged.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1971/48/section/1/1)): “A person who without lawful excuse destroys or damages any property belonging to another”
Query (legal-rag-router uk-concept-0048): `destroying damaging property belonging to another without lawful excuse`
- **vdev-0070** · `grounded_paraphrase` → **EMIT**  
  Sentence: Criminal damage committed by fire is charged as arson.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1971/48/section/1/3)): “An offence committed under this section by destroying or damaging property by fire shall be charged as arson.”
Query (legal-rag-router uk-concept-0048): `destroying damaging property belonging to another without lawful excuse`
- **vdev-0071** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Arson is charged under section 1(3) of the Criminal Damage Act 1981.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1971/48/section/1/3)): “shall be charged as arson”
Query (legal-rag-router uk-concept-0048): `destroying damaging property belonging to another without lawful excuse`
- **vdev-0072** · `modal_shift` → **ROLLBACK**  
  Sentence: Damage caused by fire may be charged as arson.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1971/48/section/1/3)): “shall be charged as arson”

## uk/ukpga/1997/40/s2 + uk/ukpga/1997/40/s1

Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0073** · `grounded_paraphrase` → **EMIT**  
  Sentence: Harassment under section 2 is a summary offence punishable by up to six months' imprisonment, a fine, or both.  
  Source ([s2/2](https://www.legislation.gov.uk/ukpga/1997/40/section/2/2)): “imprisonment for a term not exceeding six months, or a fine not exceeding level 5 on the standard scale, or both”
Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0074** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is a defence to show that the course of conduct was pursued to prevent or detect crime.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1997/40/section/1/3)): “that it was pursued for the purpose of preventing or detecting crime”
Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0075** · `grounded_paraphrase` → **EMIT**  
  Sentence: A person ought to know their conduct is harassment if a reasonable person with the same information would think so.  
  Source ([s1/2](https://www.legislation.gov.uk/ukpga/1997/40/section/1/2)): “if a reasonable person in possession of the same information would think the course of conduct amounted to harassment”
Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0076** · `wrong_figure` → **ROLLBACK**  
  Sentence: Harassment under section 2 carries a maximum of twelve months' imprisonment on summary conviction.  
  Source ([s2/2](https://www.legislation.gov.uk/ukpga/1997/40/section/2/2)): “imprisonment for a term not exceeding six months”
Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0077** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: Harassment under section 2 is punishable by six months' imprisonment.  
  Source ([s2/2](https://www.legislation.gov.uk/ukpga/1997/40/section/2/2)): “not exceeding six months”
Query (legal-rag-router uk-concept-0051): `course of conduct harassment criminal offence`
- **vdev-0078** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Under the Protection from Harassment Act 1998, pursuing a course of harassing conduct is a criminal offence.  
  Source ([s2/1](https://www.legislation.gov.uk/ukpga/1997/40/section/2/1)): “A person who pursues a course of conduct in breach of section 1(1) or (1A) is guilty of an offence.”

## uk/ukpga/1986/64/s4

Query (legal-rag-router uk-concept-0053): `threatening abusive words fear of immediate unlawful violence`
- **vdev-0079** · `grounded_paraphrase` → **EMIT**  
  Sentence: A section 4 offence can be committed in either a public or a private place.  
  Source ([s4/2](https://www.legislation.gov.uk/ukpga/1986/64/section/4/2)): “An offence under this section may be committed in a public or a private place”
Query (legal-rag-router uk-concept-0053): `threatening abusive words fear of immediate unlawful violence`
- **vdev-0080** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The offence can be committed anywhere, including between two people inside the same house.  
  Source ([s4/2](https://www.legislation.gov.uk/ukpga/1986/64/section/4/2)): “no offence is committed where the words or behaviour are used”
Query (legal-rag-router uk-concept-0053): `threatening abusive words fear of immediate unlawful violence`
- **vdev-0081** · `wrong_figure` → **ROLLBACK**  
  Sentence: The maximum penalty is 51 weeks' imprisonment.  
  Source ([s4/4](https://www.legislation.gov.uk/ukpga/1986/64/section/4/4)): “imprisonment for a term not exceeding 6 months”
Query (legal-rag-router uk-concept-0053): `threatening abusive words fear of immediate unlawful violence`
- **vdev-0082** · `connective` → **EMIT**  
  Sentence: Several points follow from this.  
  Source ([s4/1](https://www.legislation.gov.uk/ukpga/1986/64/section/4/1)): “A person is guilty of an offence if he”

## uk/ukpga/1984/60/s78

Query (legal-rag-router uk-concept-0061): `court exclude prosecution evidence adverse effect fairness proceedings`
- **vdev-0083** · `grounded_paraphrase` → **EMIT**  
  Sentence: The court may refuse to admit prosecution evidence if admitting it would have such an adverse effect on the fairness of the proceedings that it ought not to be admitted.  
  Source ([s78/1](https://www.legislation.gov.uk/ukpga/1984/60/section/78/1)): “the court may refuse to allow evidence on which the prosecution proposes to rely”
Query (legal-rag-router uk-concept-0061): `court exclude prosecution evidence adverse effect fairness proceedings`
- **vdev-0084** · `grounded_paraphrase` → **EMIT**  
  Sentence: Section 78 does not affect any rule of law that requires a court to exclude evidence.  
  Source ([s78/2](https://www.legislation.gov.uk/ukpga/1984/60/section/78/2)): “Nothing in this section shall prejudice any rule of law requiring a court to exclude evidence.”
Query (legal-rag-router uk-concept-0061): `court exclude prosecution evidence adverse effect fairness proceedings`
- **vdev-0085** · `modal_shift` → **ROLLBACK**  
  Sentence: The court must exclude any prosecution evidence that was obtained unfairly.  
  Source ([s78/1](https://www.legislation.gov.uk/ukpga/1984/60/section/78/1)): “the court may refuse to allow evidence”
Query (legal-rag-router uk-concept-0061): `court exclude prosecution evidence adverse effect fairness proceedings`
- **vdev-0086** · `connective` → **EMIT**  
  Sentence: Let me explain the relevant provision.  
  Source ([s78/1](https://www.legislation.gov.uk/ukpga/1984/60/section/78/1)): “In any proceedings the court may refuse to allow evidence”

## uk/ukpga/1984/60/s76

Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0087** · `grounded_paraphrase` → **EMIT**  
  Sentence: If a confession may have been obtained by oppression, the court must not admit it unless the prosecution proves beyond reasonable doubt that it was not obtained in that way.  
  Source ([s76/2](https://www.legislation.gov.uk/ukpga/1984/60/section/76/2)): “the court shall not allow the confession to be given in evidence against him except in so far as the prosecution proves to the court beyond reasonable doubt”
Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0088** · `grounded_paraphrase` → **EMIT**  
  Sentence: Oppression includes torture, inhuman or degrading treatment, and the use or threat of violence.  
  Source ([s76/8](https://www.legislation.gov.uk/ukpga/1984/60/section/76/8)): ““oppression” includes torture, inhuman or degrading treatment, and the use or threat of violence”
Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0089** · `grounded_paraphrase` → **EMIT**  
  Sentence: Excluding a confession does not stop facts discovered as a result of it from being admitted.  
  Source ([s76/4](https://www.legislation.gov.uk/ukpga/1984/60/section/76/4)): “shall not affect the admissibility in evidence— (a) of any facts discovered as a result of the confession”
Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0090** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The prosecution only has to prove on the balance of probabilities that the confession was not obtained by oppression.  
  Source ([s76/2](https://www.legislation.gov.uk/ukpga/1984/60/section/76/2)): “the prosecution proves to the court beyond reasonable doubt”
Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0091** · `modal_shift` → **ROLLBACK**  
  Sentence: The court may let such a confession in even if the prosecution cannot prove it was not obtained by oppression.  
  Source ([s76/2](https://www.legislation.gov.uk/ukpga/1984/60/section/76/2)): “the court shall not allow the confession to be given in evidence”
Query (legal-rag-router uk-concept-0062): `confession obtained by oppression inadmissible`
- **vdev-0092** · `wrong_citation` → **ROLLBACK**  
  Sentence: Oppression is defined in section 76(9) of the Act.  
  Source ([s76/8](https://www.legislation.gov.uk/ukpga/1984/60/section/76/8)): “In this section “oppression” includes”

## uk/ukpga/1994/33/s34

Query (legal-rag-router uk-concept-0064): `adverse inference failure mention fact police interview silence`
- **vdev-0093** · `grounded_paraphrase` → **EMIT**  
  Sentence: If, when questioned under caution, the accused failed to mention a fact they later rely on in their defence, the court or jury may draw such inferences as appear proper.  
  Source ([s34/2](https://www.legislation.gov.uk/ukpga/1994/33/section/34/2)): “may draw such inferences from the failure as appear proper”
Query (legal-rag-router uk-concept-0064): `adverse inference failure mention fact police interview silence`
- **vdev-0094** · `grounded_paraphrase` → **EMIT**  
  Sentence: At an authorised place of detention, no inference can be drawn if the accused had not been allowed to consult a solicitor before being questioned.  
  Source ([s34/2A](https://www.legislation.gov.uk/ukpga/1994/33/section/34/2A)): “subsections (1) and (2) above do not apply if he had not been allowed an opportunity to consult a solicitor”
Query (legal-rag-router uk-concept-0064): `adverse inference failure mention fact police interview silence`
- **vdev-0095** · `modal_shift` → **ROLLBACK**  
  Sentence: The jury must draw an adverse inference whenever the accused stayed silent in interview.  
  Source ([s34/2](https://www.legislation.gov.uk/ukpga/1994/33/section/34/2)): “may draw such inferences from the failure as appear proper”
Query (legal-rag-router uk-concept-0064): `adverse inference failure mention fact police interview silence`
- **vdev-0096** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Section 34 of the Police and Criminal Evidence Act 1984 allows adverse inferences from silence in interview.  
  Source ([s34/1](https://www.legislation.gov.uk/ukpga/1994/33/section/34/1)): “on being questioned under caution by a constable”

## uk/ukpga/1974/53/s1 + uk/ukpga/1974/53/s4 + uk/ukpga/1974/53/s5

Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0097** · `grounded_paraphrase` → **EMIT**  
  Sentence: Once a conviction is spent, the person is treated in law as if they had not committed or been convicted of the offence.  
  Source ([s4/1](https://www.legislation.gov.uk/ukpga/1974/53/section/4/1)): “shall be treated for all purposes in law as a person who has not committed or been charged with or prosecuted for or convicted of”
Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0098** · `grounded_paraphrase` → **EMIT**  
  Sentence: A spent conviction is not a proper ground for dismissing someone or excluding them from employment.  
  Source ([s4/3](https://www.legislation.gov.uk/ukpga/1974/53/section/4/3)): “shall not be a proper ground for dismissing or excluding a person from any office, profession, occupation or employment”
Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0099** · `grounded_paraphrase` → **EMIT**  
  Sentence: The Act does not apply to convictions for offences committed when the person was under 12.  
  Source ([s1/7](https://www.legislation.gov.uk/ukpga/1974/53/section/1/7)): “This Act does not apply to any conviction of an offence committed when the individual was under 12 years of age.”
Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0100** · `wrong_figure` → **ROLLBACK**  
  Sentence: Sentences of more than 2 years for serious violent, sexual or terrorism offences are excluded from rehabilitation.  
  Source ([s5](https://www.legislation.gov.uk/ukpga/1974/53/section/5)): “a sentence of imprisonment for a term exceeding 4 years”
Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0101** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A job applicant must disclose a spent conviction if the employer asks about previous convictions.  
  Source ([s4/2](https://www.legislation.gov.uk/ukpga/1974/53/section/4/2)): “the question shall be treated as not relating to spent convictions”
Query (legal-rag-router uk-concept-0071): `spent convictions rehabilitation period job applicant disclosure`
- **vdev-0102** · `connective` → **EMIT**  
  Sentence: To summarise:  
  Source ([s4/1](https://www.legislation.gov.uk/ukpga/1974/53/section/4/1)): “a person who has become a rehabilitated protected person”

## uk/ukpga/1985/70/s11

Query (legal-rag-router uk-concept-0074): `landlord repair structure exterior short residential lease`
- **vdev-0103** · `grounded_paraphrase` → **EMIT**  
  Sentence: The landlord may enter to view the condition of the premises at reasonable times of the day after giving 24 hours' notice in writing to the occupier.  
  Source ([s11/6](https://www.legislation.gov.uk/ukpga/1985/70/section/11/6)): “may at reasonable times of the day and on giving 24 hours’ notice in writing to the occupier, enter the premises”
Query (legal-rag-router uk-concept-0074): `landlord repair structure exterior short residential lease`
- **vdev-0104** · `grounded_paraphrase` → **EMIT**  
  Sentence: The landlord does not have to repair or maintain anything the tenant is entitled to remove from the dwelling.  
  Source ([s11/2](https://www.legislation.gov.uk/ukpga/1985/70/section/11/2)): “to keep in repair or maintain anything which the lessee is entitled to remove from the dwelling-house”
Query (legal-rag-router uk-concept-0074): `landlord repair structure exterior short residential lease`
- **vdev-0105** · `wrong_figure` → **ROLLBACK**  
  Sentence: The landlord must give 48 hours' written notice before entering to inspect.  
  Source ([s11/6](https://www.legislation.gov.uk/ukpga/1985/70/section/11/6)): “on giving 24 hours’ notice in writing to the occupier”
Query (legal-rag-router uk-concept-0074): `landlord repair structure exterior short residential lease`
- **vdev-0106** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The landlord's repairing obligation includes rebuilding the property after a fire.  
  Source ([s11/2](https://www.legislation.gov.uk/ukpga/1985/70/section/11/2)): “to rebuild or reinstate the premises in the case of destruction or damage by fire”
Query (legal-rag-router uk-concept-0074): `landlord repair structure exterior short residential lease`
- **vdev-0107** · `wrong_citation` → **ROLLBACK**  
  Sentence: The repairing covenant is implied by section 11(1) of the Landlord and Tenant Act 1985 and limited by section 11(9).  
  Source ([s11/1](https://www.legislation.gov.uk/ukpga/1985/70/section/11/1)): “there is implied a covenant by the lessor”

## uk/ukpga/1988/50/s13

Query (legal-rag-router uk-concept-0078): `landlord increase rent periodic assured tenancy notice`
- **vdev-0108** · `grounded_paraphrase` → **EMIT**  
  Sentence: For a yearly tenancy, the minimum period before a proposed rent increase can take effect is six months.  
  Source ([s13/3](https://www.legislation.gov.uk/ukpga/1988/50/section/13/3)): “(a) in the case of a yearly tenancy, six months”
Query (legal-rag-router uk-concept-0078): `landlord increase rent periodic assured tenancy notice`
- **vdev-0109** · `grounded_paraphrase` → **EMIT**  
  Sentence: The new rent takes effect as stated in the notice unless, before the new period begins, the tenant refers it to the tribunal or the parties agree a different rent.  
  Source ([s13/4](https://www.legislation.gov.uk/ukpga/1988/50/section/13/4)): “a new rent specified in the notice shall take effect as mentioned in the notice unless, before the beginning of the new period specified in the notice”
Query (legal-rag-router uk-concept-0078): `landlord increase rent periodic assured tenancy notice`
- **vdev-0110** · `value_swap` → **ROLLBACK**  
  Sentence: For a monthly periodic tenancy, the landlord's notice must allow at least six months before the new rent takes effect.  
  Source ([s13/3](https://www.legislation.gov.uk/ukpga/1988/50/section/13/3)): “(c) in any other case, a period equal to the period of the tenancy”
Query (legal-rag-router uk-concept-0078): `landlord increase rent periodic assured tenancy notice`
- **vdev-0111** · `wrong_figure` → **ROLLBACK**  
  Sentence: A further increase cannot normally take effect until 60 weeks after the last one.  
  Source ([s13/3A](https://www.legislation.gov.uk/ukpga/1988/50/section/13/3A)): “the date that falls 52 weeks after the date on which the increased rent took effect”

## uk/ukpga/1977/43/s5

Query (legal-rag-router uk-concept-0082): `notice to quit dwelling minimum four weeks`
- **vdev-0112** · `grounded_paraphrase` → **EMIT**  
  Sentence: A notice to quit a dwelling is only valid if it is in writing and given at least four weeks before it is to take effect.  
  Source ([s5/1](https://www.legislation.gov.uk/ukpga/1977/43/section/5/1)): “it is given not less than 4 weeks before the date on which it is to take effect”
Query (legal-rag-router uk-concept-0082): `notice to quit dwelling minimum four weeks`
- **vdev-0113** · `grounded_paraphrase` → **EMIT**  
  Sentence: Without a written agreement with the landlord, an assured tenant's notice to quit must be given at least two months before it takes effect.  
  Source ([s5/1ZA](https://www.legislation.gov.uk/ukpga/1977/43/section/5/1ZA)): “in the absence of agreement under sub-paragraph (i), not less than two months before the date on which the notice is to take effect”
Query (legal-rag-router uk-concept-0082): `notice to quit dwelling minimum four weeks`
- **vdev-0114** · `grounded_paraphrase` → **EMIT**  
  Sentence: A notice to quit a dwelling must be given four weeks before it takes effect.  
  Source ([s5/1](https://www.legislation.gov.uk/ukpga/1977/43/section/5/1)): “not less than 4 weeks before the date on which it is to take effect”  
  Note: Relabelled 2026-10-05 (stop 6): states the statutory minimum as the threshold to meet; see legal-rag-audit defects 23 and 29.
Query (legal-rag-router uk-concept-0082): `notice to quit dwelling minimum four weeks`
- **vdev-0115** · `wrong_figure` → **ROLLBACK**  
  Sentence: An assured tenant must give at least three months' notice to quit unless the landlord agrees to less.  
  Source ([s5/1ZA](https://www.legislation.gov.uk/ukpga/1977/43/section/5/1ZA)): “not less than two months before the date on which the notice is to take effect”
Query (legal-rag-router uk-concept-0082): `notice to quit dwelling minimum four weeks`
- **vdev-0116** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A notice to quit can be given orally if both parties agree.  
  Source ([s5/1](https://www.legislation.gov.uk/ukpga/1977/43/section/5/1)): “(a) it is in writing and contains such information as may be prescribed”

## uk/ukpga/1985/68/s118

Query (legal-rag-router uk-concept-0087): `council tenant right to buy home`
- **vdev-0117** · `grounded_paraphrase` → **EMIT**  
  Sentence: A secure tenant of a house in England has the right to buy, which means acquiring the freehold if the landlord owns it.  
  Source ([s118/1](https://www.legislation.gov.uk/ukpga/1985/68/section/118/1)): “if the dwelling-house is a house and the landlord owns the freehold, to acquire the freehold of the dwelling-house”
Query (legal-rag-router uk-concept-0087): `council tenant right to buy home`
- **vdev-0118** · `grounded_paraphrase` → **EMIT**  
  Sentence: If the home is a flat, the right to buy is a right to be granted a lease.  
  Source ([s118/1](https://www.legislation.gov.uk/ukpga/1985/68/section/118/1)): “if the dwelling-house is a flat (whether or not the landlord owns the freehold), to be granted a lease of the dwelling-house”
Query (legal-rag-router uk-concept-0087): `council tenant right to buy home`
- **vdev-0119** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A secure tenant must have been a public sector tenant for at least three years before exercising the right to buy.  
  Source ([s118/1](https://www.legislation.gov.uk/ukpga/1985/68/section/118/1)): “in the circumstances and subject to the conditions and exceptions stated in the following provisions of this Part”  
  Note: True in law (s.119) but not in this premise.
Query (legal-rag-router uk-concept-0087): `council tenant right to buy home`
- **vdev-0120** · `wrong_instrument` → **ROLLBACK**  
  Sentence: The right to buy is set out in section 118 of the Housing Act 1988.  
  Source ([s118/1](https://www.legislation.gov.uk/ukpga/1985/68/section/118/1)): “A secure tenant of a dwelling-house in England has the right to buy”

## uk/ukpga/2002/9/sch6 + uk/ukpga/2002/9/s97

Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0121** · `grounded_paraphrase` → **EMIT**  
  Sentence: A squatter can apply to be registered as proprietor once they have been in adverse possession for ten years ending on the date of the application.  
  Source ([sch6/para1](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/1)): “if he has been in adverse possession of the estate for the period of ten years ending on the date of the application”
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0122** · `grounded_paraphrase` → **EMIT**  
  Sentence: Where the land is Crown foreshore, the ten-year period is read as sixty years.  
  Source ([sch6/para13](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/13)): “paragraph 1(1) is to have effect as if the reference to ten years were to sixty years”
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0123** · `grounded_paraphrase` → **EMIT**  
  Sentence: The registrar must notify the registered proprietor of the squatter's application.  
  Source ([sch6/para2](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/2)): “The registrar must give notice of an application under paragraph 1 to— (a) the proprietor of the estate to which the application relates”
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0124** · `wrong_figure` → **ROLLBACK**  
  Sentence: A squatter can apply to be registered after twelve years of adverse possession of registered land.  
  Source ([sch6/para1](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/1)): “for the period of ten years ending on the date of the application”  
  Note: Twelve years is the unregistered-land limitation period; not in this premise.
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0125** · `modal_shift` → **ROLLBACK**  
  Sentence: The registrar may give notice of the application to the registered proprietor.  
  Source ([sch6/para2](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/2)): “The registrar must give notice of an application under paragraph 1”
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0126** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: After ten years the squatter automatically becomes the registered owner without needing to apply.  
  Source ([sch6/para1](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/1)): “A person may apply to the registrar to be registered as the proprietor”
Query (legal-rag-router uk-concept-0094): `squatter adverse possession registered land ten years application`
- **vdev-0127** · `wrong_citation` → **ROLLBACK**  
  Sentence: The boundary condition is set out in paragraph 5(6) of Schedule 6.  
  Source ([sch6/para5](https://www.legislation.gov.uk/ukpga/2002/9/schedule/6/paragraph/5)): “The third condition is that— (a) the land to which the application relates is adjacent to land belonging to the applicant”

## uk/ukpga/Will4/2-3/71/s2

Query (legal-rag-router uk-concept-0102): `right of way twenty years use prescription`
- **vdev-0128** · `grounded_paraphrase` → **EMIT**  
  Sentence: A claim to a right of way enjoyed without interruption for the full twenty years cannot be defeated just by showing the use began before that period.  
  Source ([71/s2](https://www.legislation.gov.uk/ukpga/Will4/2-3/71/section/2)): “shall be defeated or destroyed by showing only that such way or other matter was first enjoyed at any time prior to such period of twenty years”
Query (legal-rag-router uk-concept-0102): `right of way twenty years use prescription`
- **vdev-0129** · `grounded_paraphrase` → **EMIT**  
  Sentence: After forty years of uninterrupted enjoyment the right is absolute and indefeasible unless it was enjoyed by written consent.  
  Source ([71/s2](https://www.legislation.gov.uk/ukpga/Will4/2-3/71/section/2)): “for the full period of forty years, the right thereto shall be deemed absolute and indefeasible”
Query (legal-rag-router uk-concept-0102): `right of way twenty years use prescription`
- **vdev-0130** · `value_swap` → **ROLLBACK**  
  Sentence: A right of way becomes absolute and indefeasible after twenty years of uninterrupted use.  
  Source ([71/s2](https://www.legislation.gov.uk/ukpga/Will4/2-3/71/section/2)): “for the full period of forty years, the right thereto shall be deemed absolute and indefeasible”

## uk/ukpga/Geo5/15-16/20/s146

Query (legal-rag-router uk-concept-0093): `landlord forfeiture breach covenant notice specifying breach relief`
- **vdev-0131** · `grounded_paraphrase` → **EMIT**  
  Sentence: Before forfeiting a lease for breach of covenant, the landlord must serve a notice specifying the breach, requiring it to be remedied if it can be, and requiring compensation.  
  Source ([20/s146/1](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/1)): “unless and until the lessor serves on the lessee a notice— (a) specifying the particular breach complained of”
Query (legal-rag-router uk-concept-0093): `landlord forfeiture breach covenant notice specifying breach relief`
- **vdev-0132** · `grounded_paraphrase` → **EMIT**  
  Sentence: The tenant can apply to the court for relief, which the court may grant or refuse as it thinks fit.  
  Source ([20/s146/2](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/2)): “the lessee may, in the lessor’s action, if any, or in any action brought by himself, apply to the court for relief”
Query (legal-rag-router uk-concept-0093): `landlord forfeiture breach covenant notice specifying breach relief`
- **vdev-0133** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Section 146 of the Landlord and Tenant Act 1985 requires a notice before forfeiture.  
  Source ([20/s146/1](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/1)): “unless and until the lessor serves on the lessee a notice”
Query (legal-rag-router uk-concept-0093): `landlord forfeiture breach covenant notice specifying breach relief`
- **vdev-0134** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Forfeiture for non-payment of rent also requires a section 146 notice.  
  Source ([20/s146/11](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/11)): “This section does not, save as otherwise mentioned, affect the law relating to re-entry or forfeiture or relief in case of non-payment of rent.”

## uk/ukpga/Geo5/15-16/20/s101

Query (legal-rag-router uk-concept-0103): `mortgage lender power of sale arrears`
- **vdev-0135** · `grounded_paraphrase` → **EMIT**  
  Sentence: Where the mortgage is made by deed, the lender has a power to sell the mortgaged property once the mortgage money has become due.  
  Source ([20/s101/1](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/101/1)): “A power, when the mortgage money has become due, to sell”
Query (legal-rag-router uk-concept-0103): `mortgage lender power of sale arrears`
- **vdev-0136** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The lender must obtain a court order before exercising the power of sale.  
  Source ([20/s101/1](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/101/1)): “by public auction or by private contract”

## uk/ukpga/2006/46/s174

Query (legal-rag-router uk-false_abstention-0019): `Companies Act 2006 Pt 10 Ch 2`
- **vdev-0137** · `grounded_paraphrase` → **EMIT**  
  Sentence: A director must exercise reasonable care, skill and diligence.  
  Source ([s174/1](https://www.legislation.gov.uk/ukpga/2006/46/section/174/1)): “A director of a company must exercise reasonable care, skill and diligence.”
Query (legal-rag-router uk-concept-0106): `director negligence standard reasonable care skill diligence`
- **vdev-0138** · `grounded_paraphrase` → **EMIT**  
  Sentence: The standard is that of a reasonably diligent person with the knowledge, skill and experience that may reasonably be expected of someone in the director's role, and the director's own knowledge, skill and experience.  
  Source ([s174/2](https://www.legislation.gov.uk/ukpga/2006/46/section/174/2)): “the care, skill and diligence that would be exercised by a reasonably diligent person”
Query (legal-rag-router uk-concept-0106): `director negligence standard reasonable care skill diligence`
- **vdev-0139** · `modal_shift` → **ROLLBACK**  
  Sentence: Directors are expected, but not legally required, to exercise reasonable care, skill and diligence.  
  Source ([s174/1](https://www.legislation.gov.uk/ukpga/2006/46/section/174/1)): “A director of a company must exercise reasonable care, skill and diligence.”

## uk/ukpga/2006/46/s175

Query (legal-rag-router uk-concept-0105): `director duty avoid conflict of interest`
- **vdev-0140** · `grounded_paraphrase` → **EMIT**  
  Sentence: A director must avoid situations in which they have, or could have, an interest that conflicts with the company's interests.  
  Source ([s175/1](https://www.legislation.gov.uk/ukpga/2006/46/section/175/1)): “must avoid a situation in which he has, or can have, a direct or indirect interest that conflicts”
Query (legal-rag-router uk-concept-0105): `director duty avoid conflict of interest`
- **vdev-0141** · `grounded_paraphrase` → **EMIT**  
  Sentence: The duty is not infringed if the matter has been authorised by the directors.  
  Source ([s175/4](https://www.legislation.gov.uk/ukpga/2006/46/section/175/4)): “This duty is not infringed— (a) if the situation cannot reasonably be regarded as likely to give rise to a conflict of interest; or (b) if the matter has been authorised by the directors.”
Query (legal-rag-router uk-concept-0105): `director duty avoid conflict of interest`
- **vdev-0142** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: In a public company, the directors can authorise a conflict of interest.  
  Source ([s175/5](https://www.legislation.gov.uk/ukpga/2006/46/section/175/5)): “where the company is a public company and its constitution includes provision enabling the directors to authorise the matter”  
  Note: Drops the condition that the constitution must enable authorisation.
Query (legal-rag-router uk-false_abstention-0019): `Companies Act 2006 Pt 10 Ch 2`
- **vdev-0143** · `wrong_citation` → **ROLLBACK**  
  Sentence: Under section 175(3), the duty is not infringed if the situation cannot reasonably be regarded as likely to give rise to a conflict of interest.  
  Source ([s175/4](https://www.legislation.gov.uk/ukpga/2006/46/section/175/4)): “This duty is not infringed— (a) if the situation cannot reasonably be regarded”  
  Note: Misattributed: this is s.175(4)(a); s.175(3) exists but says something else.

## uk/ukpga/2006/46/s168

Query (legal-rag-router uk-concept-0114): `remove director ordinary resolution notice`
- **vdev-0144** · `grounded_paraphrase` → **EMIT**  
  Sentence: A company can remove a director by ordinary resolution at a meeting, despite anything in an agreement between them.  
  Source ([s168/1](https://www.legislation.gov.uk/ukpga/2006/46/section/168/1)): “A company may by ordinary resolution at a meeting remove a director”
Query (legal-rag-router uk-concept-0114): `remove director ordinary resolution notice`
- **vdev-0145** · `grounded_paraphrase` → **EMIT**  
  Sentence: Removal does not deprive the director of compensation or damages for the termination of their appointment.  
  Source ([s168/5](https://www.legislation.gov.uk/ukpga/2006/46/section/168/5)): “as depriving a person removed under it of compensation or damages”
Query (legal-rag-router uk-concept-0114): `remove director ordinary resolution notice`
- **vdev-0146** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A company can only remove a director by special resolution.  
  Source ([s168/1](https://www.legislation.gov.uk/ukpga/2006/46/section/168/1)): “A company may by ordinary resolution at a meeting remove a director”

## uk/ukpga/2006/46/s21

Query (legal-rag-router uk-concept-0117): `amend articles of association special resolution`
- **vdev-0147** · `grounded_paraphrase` → **EMIT**  
  Sentence: A company may change its articles of association by special resolution.  
  Source ([s21/1](https://www.legislation.gov.uk/ukpga/2006/46/section/21/1)): “A company may amend its articles by special resolution.”

## uk/ukpga/2006/46/s994

Query (legal-rag-router uk-concept-0108): `minority shareholder unfairly prejudicial conduct petition`
- **vdev-0148** · `grounded_paraphrase` → **EMIT**  
  Sentence: A member can petition the court on the ground that the company's affairs are being conducted in a way that is unfairly prejudicial to members' interests, including their own.  
  Source ([s994/1](https://www.legislation.gov.uk/ukpga/2006/46/section/994/1)): “A member of a company may apply to the court by petition”
Query (legal-rag-router uk-concept-0108): `minority shareholder unfairly prejudicial conduct petition`
- **vdev-0149** · `grounded_paraphrase` → **EMIT**  
  Sentence: Removing the auditor because of differences of opinion on accounting treatments is treated as unfairly prejudicial.  
  Source ([s994/1A](https://www.legislation.gov.uk/ukpga/2006/46/section/994/1A)): “on grounds of divergence of opinions on accounting treatments or audit procedures”
Query (legal-rag-router uk-concept-0108): `minority shareholder unfairly prejudicial conduct petition`
- **vdev-0150** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Only members holding at least 10% of the shares can petition under section 994.  
  Source ([s994/1](https://www.legislation.gov.uk/ukpga/2006/46/section/994/1)): “A member of a company may apply to the court by petition”

## uk/ukpga/1986/45/s214

Query (legal-rag-router uk-concept-0122): `director continued trading knew no reasonable prospect avoiding insolvent liquidation`
- **vdev-0151** · `grounded_paraphrase` → **EMIT**  
  Sentence: The court can order a director to contribute to the company's assets if they knew, or ought to have concluded, that there was no reasonable prospect of avoiding insolvent liquidation.  
  Source ([s214/2](https://www.legislation.gov.uk/ukpga/1986/45/section/214/2)): “that person knew or ought to have concluded that there was no reasonable prospect that the company would avoid going into insolvent liquidation”
Query (legal-rag-router uk-concept-0122): `director continued trading knew no reasonable prospect avoiding insolvent liquidation`
- **vdev-0152** · `grounded_paraphrase` → **EMIT**  
  Sentence: For this purpose a shadow director counts as a director.  
  Source ([s214/7](https://www.legislation.gov.uk/ukpga/1986/45/section/214/7)): “In this section “director” includes a shadow director.”
Query (legal-rag-router uk-concept-0122): `director continued trading knew no reasonable prospect avoiding insolvent liquidation`
- **vdev-0153** · `wrong_figure` → **ROLLBACK**  
  Sentence: No declaration can be made where the relevant time was before 28 April 1989.  
  Source ([s214/2](https://www.legislation.gov.uk/ukpga/1986/45/section/214/2)): “was before 28th April 1986”
Query (legal-rag-router uk-concept-0122): `director continued trading knew no reasonable prospect avoiding insolvent liquidation`
- **vdev-0154** · `wrong_citation` → **ROLLBACK**  
  Sentence: The defence in section 214(5) protects a director who took every step to minimise the potential loss to creditors.  
  Source ([s214/3](https://www.legislation.gov.uk/ukpga/1986/45/section/214/3)): “that person took every step with a view to minimising the potential loss”  
  Note: Misattributed: the defence is s.214(3); s.214(5) exists.

## uk/ukpga/1986/45/s238

Query (legal-rag-router uk-concept-0124): `company sold asset undervalue before liquidation set aside`
- **vdev-0155** · `grounded_paraphrase` → **EMIT**  
  Sentence: A transaction at an undervalue includes a gift by the company, or a deal in which the company receives significantly less than it provides.  
  Source ([s238/4](https://www.legislation.gov.uk/ukpga/1986/45/section/238/4)): “the company makes a gift to that person”
Query (legal-rag-router uk-concept-0124): `company sold asset undervalue before liquidation set aside`
- **vdev-0156** · `grounded_paraphrase` → **EMIT**  
  Sentence: No order is made if the company acted in good faith for the purpose of its business with reasonable grounds for believing the transaction would benefit it.  
  Source ([s238/5](https://www.legislation.gov.uk/ukpga/1986/45/section/238/5)): “did so in good faith and for the purpose of carrying on its business”
Query (legal-rag-router uk-concept-0124): `company sold asset undervalue before liquidation set aside`
- **vdev-0157** · `modal_shift` → **ROLLBACK**  
  Sentence: On the office-holder's application, the court may make whatever order it thinks fit to restore the position.  
  Source ([s238/3](https://www.legislation.gov.uk/ukpga/1986/45/section/238/3)): “the court shall, on such an application, make such order as it thinks fit”
Query (legal-rag-router uk-concept-0124): `company sold asset undervalue before liquidation set aside`
- **vdev-0158** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Transactions within five years before insolvency can be set aside as undervalues.  
  Source ([s238/2](https://www.legislation.gov.uk/ukpga/1986/45/section/238/2)): “at a relevant time (defined in section 240)”  
  Note: The relevant time is in s.240 (not in the premise); five years is wrong in any case.

## uk/ukpga/1986/45/s239

Query (legal-rag-router uk-concept-0125): `paying one creditor ahead of others preference desire`
- **vdev-0159** · `grounded_paraphrase` → **EMIT**  
  Sentence: Where the preference was given to a connected person, the desire to prefer is presumed unless the contrary is shown.  
  Source ([s239/6](https://www.legislation.gov.uk/ukpga/1986/45/section/239/6)): “is presumed, unless the contrary is shown”
Query (legal-rag-router uk-concept-0125): `paying one creditor ahead of others preference desire`
- **vdev-0160** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Any payment to one creditor ahead of the others is automatically a preference that can be reversed.  
  Source ([s239/5](https://www.legislation.gov.uk/ukpga/1986/45/section/239/5)): “unless the company which gave the preference was influenced in deciding to give it by a desire”

## uk/ukpga/1986/45/s279

Query (legal-rag-router uk-concept-0130): `bankrupt automatic discharge after one year`
- **vdev-0161** · `grounded_paraphrase` → **EMIT**  
  Sentence: A bankrupt is discharged one year after the bankruptcy commences.  
  Source ([s279/1](https://www.legislation.gov.uk/ukpga/1986/45/section/279/1)): “at the end of the period of one year beginning with the date on which the bankruptcy commences”
Query (legal-rag-router uk-concept-0130): `bankrupt automatic discharge after one year`
- **vdev-0162** · `wrong_figure` → **ROLLBACK**  
  Sentence: A bankrupt is discharged three years after the bankruptcy commences.  
  Source ([s279/1](https://www.legislation.gov.uk/ukpga/1986/45/section/279/1)): “at the end of the period of one year”
Query (legal-rag-router uk-concept-0130): `bankrupt automatic discharge after one year`
- **vdev-0163** · `modal_shift` → **ROLLBACK**  
  Sentence: The court must suspend the discharge period whenever the trustee applies.  
  Source ([s279/4](https://www.legislation.gov.uk/ukpga/1986/45/section/279/4)): “The court may make an order under subsection (3) only if satisfied”

## uk/ukpga/1986/45/s84

Query (legal-rag-router uk-concept-0134): `members resolution voluntary winding up`
- **vdev-0164** · `grounded_paraphrase` → **EMIT**  
  Sentence: A company can be wound up voluntarily if it resolves by special resolution to do so.  
  Source ([s84/1](https://www.legislation.gov.uk/ukpga/1986/45/section/84/1)): “if the company resolves by special resolution that it be wound up voluntarily”
Query (legal-rag-router uk-concept-0134): `members resolution voluntary winding up`
- **vdev-0165** · `wrong_figure` → **ROLLBACK**  
  Sentence: Once a qualifying floating charge holder has been given notice, the resolution can only be passed after ten business days unless they consent in writing.  
  Source ([s84/2B](https://www.legislation.gov.uk/ukpga/1986/45/section/84/2B)): “after the end of the period of five business days”

## uk/ukpga/2015/15/s23

Query (legal-rag-router uk-concept-0137): `faulty goods consumer right repair or replacement`
- **vdev-0166** · `grounded_paraphrase` → **EMIT**  
  Sentence: The trader must repair or replace the goods within a reasonable time and without significant inconvenience, and bear the necessary costs such as labour, materials and postage.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/2015/15/section/23/2)): “do so within a reasonable time and without significant inconvenience to the consumer”
Query (legal-rag-router uk-concept-0137): `faulty goods consumer right repair or replacement`
- **vdev-0167** · `grounded_paraphrase` → **EMIT**  
  Sentence: The consumer cannot insist on repair or replacement if that remedy is impossible or disproportionate compared to the other.  
  Source ([s23/3](https://www.legislation.gov.uk/ukpga/2015/15/section/23/3)): “The consumer cannot require the trader to repair or replace the goods”
Query (legal-rag-router uk-concept-0137): `faulty goods consumer right repair or replacement`
- **vdev-0168** · `modal_shift` → **ROLLBACK**  
  Sentence: The trader may charge the consumer for the postage when repairing faulty goods.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/2015/15/section/23/2)): “bear any necessary costs incurred in doing so (including in particular the cost of any labour, materials or postage)”
Query (legal-rag-router uk-concept-0137): `faulty goods consumer right repair or replacement`
- **vdev-0169** · `wrong_instrument` → **ROLLBACK**  
  Sentence: These repair and replacement rights come from section 23 of the Sale of Goods Act 1979.  
  Source ([s23/1](https://www.legislation.gov.uk/ukpga/2015/15/section/23/1)): “This section applies if the consumer has the right to repair or replacement”
Query (legal-rag-router uk-concept-0137): `faulty goods consumer right repair or replacement`
- **vdev-0170** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The trader must complete any repair within 30 days.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/2015/15/section/23/2)): “within a reasonable time”

## uk/ukpga/2015/15/s49

Query (legal-rag-router uk-concept-0140): `trader service reasonable care and skill consumer`
- **vdev-0171** · `grounded_paraphrase` → **EMIT**  
  Sentence: Every contract to supply a service is treated as including a term that the trader must perform it with reasonable care and skill.  
  Source ([s49/1](https://www.legislation.gov.uk/ukpga/2015/15/section/49/1)): “the trader must perform the service with reasonable care and skill”
Query (legal-rag-router uk-concept-0140): `trader service reasonable care and skill consumer`
- **vdev-0172** · `grounded_paraphrase` → **EMIT**  
  Sentence: The consumer's remedies if the trader breaches that term are in section 54.  
  Source ([s49/2](https://www.legislation.gov.uk/ukpga/2015/15/section/49/2)): “See section 54 for a consumer's rights”

## uk/ukpga/2015/15/s62

Query (legal-rag-router uk-concept-0141): `unfair term consumer contract not binding`
- **vdev-0173** · `grounded_paraphrase` → **EMIT**  
  Sentence: An unfair term of a consumer contract is not binding on the consumer, although the consumer can still choose to rely on it.  
  Source ([s62/1](https://www.legislation.gov.uk/ukpga/2015/15/section/62/1)): “An unfair term of a consumer contract is not binding on the consumer.”
Query (legal-rag-router uk-concept-0141): `unfair term consumer contract not binding`
- **vdev-0174** · `grounded_paraphrase` → **EMIT**  
  Sentence: A term is unfair if, contrary to good faith, it causes a significant imbalance in the parties' rights and obligations to the consumer's detriment.  
  Source ([s62/4](https://www.legislation.gov.uk/ukpga/2015/15/section/62/4)): “contrary to the requirement of good faith, it causes a significant imbalance”
Query (legal-rag-router uk-concept-0141): `unfair term consumer contract not binding`
- **vdev-0175** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: An unfair term still binds the consumer if they signed the contract.  
  Source ([s62/1](https://www.legislation.gov.uk/ukpga/2015/15/section/62/1)): “An unfair term of a consumer contract is not binding on the consumer.”

## uk/ukpga/1977/50/s11 + uk/ukpga/1977/50/s3

Query (legal-rag-router uk-concept-0143): `exclusion clause business contract reasonableness test`
- **vdev-0176** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is for the party claiming that a term satisfies the requirement of reasonableness to show that it does.  
  Source ([s11/5](https://www.legislation.gov.uk/ukpga/1977/50/section/11/5)): “is for those claiming that a contract term or notice satisfies the requirement of reasonableness to show that it does”
Query (legal-rag-router uk-concept-0143): `exclusion clause business contract reasonableness test`
- **vdev-0177** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The party challenging an exclusion clause has to prove that it is unreasonable.  
  Source ([s11/5](https://www.legislation.gov.uk/ukpga/1977/50/section/11/5)): “is for those claiming that a contract term or notice satisfies the requirement of reasonableness to show that it does”
Query (legal-rag-router uk-concept-0143): `exclusion clause business contract reasonableness test`
- **vdev-0178** · `wrong_instrument` → **ROLLBACK**  
  Sentence: The reasonableness test for exclusion clauses is in section 11 of the Unfair Contract Terms Act 1979.  
  Source ([s11/1](https://www.legislation.gov.uk/ukpga/1977/50/section/11/1)): “the requirement of reasonableness”

## uk/ukpga/1999/31/s1

Query (legal-rag-router uk-concept-0144): `third party enforce contract term purports confer benefit`
- **vdev-0179** · `grounded_paraphrase` → **EMIT**  
  Sentence: A third party can enforce a term if the contract expressly says they may, or if the term purports to confer a benefit on them.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1999/31/section/1/1)): “(a) the contract expressly provides that he may, or (b) subject to subsection (2), the term purports to confer a benefit on him”
Query (legal-rag-router uk-concept-0144): `third party enforce contract term purports confer benefit`
- **vdev-0180** · `grounded_paraphrase` → **EMIT**  
  Sentence: The third party must be expressly identified in the contract by name, as a member of a class or by description, but need not exist when the contract is made.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1999/31/section/1/3)): “need not be in existence when the contract is entered into”
Query (legal-rag-router uk-concept-0144): `third party enforce contract term purports confer benefit`
- **vdev-0181** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A third party can enforce a term even if the contract does not identify them in any way.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/1999/31/section/1/3)): “The third party must be expressly identified in the contract”

## uk/ukpga/1998/20/s1

Query (legal-rag-router uk-concept-0151): `late payment commercial debt statutory interest`
- **vdev-0182** · `grounded_paraphrase` → **EMIT**  
  Sentence: A qualifying debt created by a contract to which the Act applies carries simple interest as an implied term.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1998/20/section/1/1)): “any qualifying debt created by the contract carries simple interest”
Query (legal-rag-router uk-concept-0151): `late payment commercial debt statutory interest`
- **vdev-0183** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Statutory interest runs at 8% above the Bank of England base rate.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1998/20/section/1/1)): “carries simple interest subject to and in accordance with this Part”  
  Note: True in law (rate set by order) but not in this premise.
Query (legal-rag-router uk-concept-0151): `late payment commercial debt statutory interest`
- **vdev-0184** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Statutory interest is compounded monthly.  
  Source ([s1/1](https://www.legislation.gov.uk/ukpga/1998/20/section/1/1)): “carries simple interest”

## uk/ukpga/2000/36/s14

Query (legal-rag-router uk-concept-0156): `vexatious repeated information request refusal`
- **vdev-0185** · `grounded_paraphrase` → **EMIT**  
  Sentence: A public authority does not have to comply with a request for information if the request is vexatious.  
  Source ([s14/1](https://www.legislation.gov.uk/ukpga/2000/36/section/14/1)): “Section 1(1) does not oblige a public authority to comply with a request for information if the request is vexatious.”
Query (legal-rag-router uk-concept-0156): `vexatious repeated information request refusal`
- **vdev-0186** · `grounded_paraphrase` → **EMIT**  
  Sentence: An authority need not answer an identical or substantially similar repeat request from the same person unless a reasonable interval has passed.  
  Source ([s14/2](https://www.legislation.gov.uk/ukpga/2000/36/section/14/2)): “unless a reasonable interval has elapsed”
Query (legal-rag-router uk-concept-0156): `vexatious repeated information request refusal`
- **vdev-0187** · `modal_shift` → **ROLLBACK**  
  Sentence: A public authority must refuse any request it considers vexatious.  
  Source ([s14/1](https://www.legislation.gov.uk/ukpga/2000/36/section/14/1)): “does not oblige a public authority to comply”
Query (legal-rag-router uk-concept-0156): `vexatious repeated information request refusal`
- **vdev-0188** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A repeat request can be refused if it is made within 60 days of the previous one.  
  Source ([s14/2](https://www.legislation.gov.uk/ukpga/2000/36/section/14/2)): “unless a reasonable interval has elapsed”

## uk/ukpga/2018/12/s171

Query (legal-rag-router uk-concept-0162): `re-identifying anonymised personal data offence`
- **vdev-0189** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is an offence knowingly or recklessly to re-identify de-identified personal data without the consent of the controller responsible for de-identifying it.  
  Source ([s171/1](https://www.legislation.gov.uk/ukpga/2018/12/section/171/1)): “It is an offence for a person knowingly or recklessly to re-identify information”
Query (legal-rag-router uk-concept-0162): `re-identifying anonymised personal data offence`
- **vdev-0190** · `grounded_paraphrase` → **EMIT**  
  Sentence: It is a defence to prove that, in the particular circumstances, the re-identification was justified as being in the public interest.  
  Source ([s171/3](https://www.legislation.gov.uk/ukpga/2018/12/section/171/3)): “in the particular circumstances, was justified as being in the public interest”
Query (legal-rag-router uk-concept-0162): `re-identifying anonymised personal data offence`
- **vdev-0191** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Re-identifying de-identified personal data is an offence under section 171 of the Data Protection Act 1998.  
  Source ([s171/1](https://www.legislation.gov.uk/ukpga/2018/12/section/171/1)): “It is an offence for a person knowingly or recklessly to re-identify information”
Query (legal-rag-router uk-concept-0162): `re-identifying anonymised personal data offence`
- **vdev-0192** · `connective` → **EMIT**  
  Sentence: This is set out below.  
  Source ([s171/1](https://www.legislation.gov.uk/ukpga/2018/12/section/171/1)): “It is an offence for a person knowingly or recklessly”

## uk/ukpga/1989/41/s31

Query (legal-rag-router uk-concept-0172): `care order threshold child suffering significant harm`
- **vdev-0193** · `grounded_paraphrase` → **EMIT**  
  Sentence: A court may only make a care order if the child is suffering, or likely to suffer, significant harm attributable to the care given or to the child being beyond parental control.  
  Source ([s31/2](https://www.legislation.gov.uk/ukpga/1989/41/section/31/2)): “that the child concerned is suffering, or is likely to suffer, significant harm”
Query (legal-rag-router uk-concept-0172): `care order threshold child suffering significant harm`
- **vdev-0194** · `grounded_paraphrase` → **EMIT**  
  Sentence: No care order can be made for a child who has reached seventeen, or sixteen if married.  
  Source ([s31/3](https://www.legislation.gov.uk/ukpga/1989/41/section/31/3)): “who has reached the age of seventeen (or sixteen, in the case of a child who is married)”
Query (legal-rag-router uk-concept-0172): `care order threshold child suffering significant harm`
- **vdev-0195** · `value_swap` → **ROLLBACK**  
  Sentence: No care order can be made for any child aged sixteen or over.  
  Source ([s31/3](https://www.legislation.gov.uk/ukpga/1989/41/section/31/3)): “who has reached the age of seventeen (or sixteen, in the case of a child who is married)”
Query (legal-rag-router uk-concept-0172): `care order threshold child suffering significant harm`
- **vdev-0196** · `modal_shift` → **ROLLBACK**  
  Sentence: Once the threshold is met, the court must make a care order.  
  Source ([s31/1](https://www.legislation.gov.uk/ukpga/1989/41/section/31/1)): “the court may make an order”

## uk/ukpga/1989/41/s44

Query (legal-rag-router uk-concept-0173): `emergency protection order remove child immediate danger`
- **vdev-0197** · `grounded_paraphrase` → **EMIT**  
  Sentence: While an emergency protection order is in force, it gives the applicant parental responsibility for the child.  
  Source ([s44/4](https://www.legislation.gov.uk/ukpga/1989/41/section/44/4)): “(c) gives the applicant parental responsibility for the child”
Query (legal-rag-router uk-concept-0173): `emergency protection order remove child immediate danger`
- **vdev-0198** · `grounded_paraphrase` → **EMIT**  
  Sentence: Intentionally obstructing the removal of a child under the order is an offence punishable by a fine not exceeding level 3 on the standard scale.  
  Source ([s44/16](https://www.legislation.gov.uk/ukpga/1989/41/section/44/16)): “a fine not exceeding level 3 on the standard scale”
Query (legal-rag-router uk-concept-0173): `emergency protection order remove child immediate danger`
- **vdev-0199** · `wrong_figure` → **ROLLBACK**  
  Sentence: Obstructing the removal is punishable by a fine of up to level 5 on the standard scale.  
  Source ([s44/16](https://www.legislation.gov.uk/ukpga/1989/41/section/44/16)): “a fine not exceeding level 3 on the standard scale”
Query (legal-rag-router uk-concept-0173): `emergency protection order remove child immediate danger`
- **vdev-0200** · `modal_shift` → **ROLLBACK**  
  Sentence: The applicant may refuse the child any contact with their parents while the order is in force.  
  Source ([s44/13](https://www.legislation.gov.uk/ukpga/1989/41/section/44/13)): “the applicant shall, subject to any direction given under subsection (6), allow the child reasonable contact with— (a) his parents”

## uk/ukpga/1973/18/s1

Query (legal-rag-router uk-concept-0175): `no fault divorce application marriage broken down irretrievably`
- **vdev-0201** · `grounded_paraphrase` → **EMIT**  
  Sentence: Either or both parties to a marriage can apply for a divorce order on the ground that the marriage has broken down irretrievably.  
  Source ([s1](https://www.legislation.gov.uk/ukpga/1973/18/section/1)): “either or both parties to a marriage may apply to the court for an order”
Query (legal-rag-router uk-concept-0175): `no fault divorce application marriage broken down irretrievably`
- **vdev-0202** · `grounded_paraphrase` → **EMIT**  
  Sentence: The court must take the statement that the marriage has broken down irretrievably as conclusive evidence of that.  
  Source ([s1](https://www.legislation.gov.uk/ukpga/1973/18/section/1)): “take the statement to be conclusive evidence that the marriage has broken down irretrievably”
Query (legal-rag-router uk-concept-0175): `no fault divorce application marriage broken down irretrievably`
- **vdev-0203** · `wrong_figure` → **ROLLBACK**  
  Sentence: A conditional order cannot be made final until 12 weeks after it is made.  
  Source ([s1](https://www.legislation.gov.uk/ukpga/1973/18/section/1)): “may not be made final before the end of the period of 6 weeks”
Query (legal-rag-router uk-concept-0175): `no fault divorce application marriage broken down irretrievably`
- **vdev-0204** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: The applicant must prove adultery, unreasonable behaviour or separation to get a divorce.  
  Source ([s1](https://www.legislation.gov.uk/ukpga/1973/18/section/1)): “must be accompanied by a statement by the applicant or applicants that the marriage has broken down irretrievably”

## uk/ukpga/1975/63/s1

Query (legal-rag-router uk-concept-0178): `dependant claim estate reasonable financial provision will`
- **vdev-0205** · `grounded_paraphrase` → **EMIT**  
  Sentence: A cohabitant can apply if they lived with the deceased in the same household as a couple for the whole of the two years before the death.  
  Source ([s1/1A](https://www.legislation.gov.uk/ukpga/1975/63/section/1/1A)): “during the whole of the period of two years ending immediately before the date when the deceased died”
Query (legal-rag-router uk-concept-0178): `dependant claim estate reasonable financial provision will`
- **vdev-0206** · `wrong_figure` → **ROLLBACK**  
  Sentence: A cohabitant must have lived with the deceased for five years to be able to apply.  
  Source ([s1/1A](https://www.legislation.gov.uk/ukpga/1975/63/section/1/1A)): “the whole of the period of two years”
Query (legal-rag-router uk-concept-0178): `dependant claim estate reasonable financial provision will`
- **vdev-0207** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: For every applicant, reasonable financial provision means only what they need for their maintenance.  
  Source ([s1/2](https://www.legislation.gov.uk/ukpga/1975/63/section/1/2)): “whether or not that provision is required for his or her maintenance”  
  Note: Drops the spouse/civil-partner standard in s.1(2)(a)-(aa).

## uk/ukpga/Will4and1Vict/7/26/s9

Query (legal-rag-router uk-concept-0179): `will signed two witnesses formal validity`
- **vdev-0208** · `grounded_paraphrase` → **EMIT**  
  Sentence: A will must be in writing and signed by the testator, or by someone else in their presence and at their direction.  
  Source ([26/s9](https://www.legislation.gov.uk/ukpga/Will4and1Vict/7/26/section/9)): “it is in writing, and signed by the testator, or by some other person in his presence and by his direction”
Query (legal-rag-router uk-concept-0179): `will signed two witnesses formal validity`
- **vdev-0209** · `grounded_paraphrase` → **EMIT**  
  Sentence: For wills made between 31 January 2020 and 31 January 2024, presence can include presence by videoconference.  
  Source ([26/s9](https://www.legislation.gov.uk/ukpga/Will4and1Vict/7/26/section/9)): “in relation to wills made on or after 31 January 2020 and on or before 31 January 2024”
Query (legal-rag-router uk-concept-0179): `will signed two witnesses formal validity`
- **vdev-0210** · `wrong_figure` → **ROLLBACK**  
  Sentence: Witnessing by video call is allowed for wills made up to 31 January 2025.  
  Source ([26/s9](https://www.legislation.gov.uk/ukpga/Will4and1Vict/7/26/section/9)): “on or before 31 January 2024”

## uk/ukpga/Will4and1Vict/7/26/s18

Query (legal-rag-router uk-concept-0180): `marriage revokes existing will`
- **vdev-0211** · `grounded_paraphrase` → **EMIT**  
  Sentence: A will made in expectation of marriage to a particular person, and intended not to be revoked by it, is not revoked by that marriage.  
  Source ([26/s18/3](https://www.legislation.gov.uk/ukpga/Will4and1Vict/7/26/section/18/3)): “the will shall not be revoked by his marriage to that person”
Query (legal-rag-router uk-concept-0180): `marriage revokes existing will`
- **vdev-0212** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: Marriage always revokes an existing will.  
  Source ([26/s18/1](https://www.legislation.gov.uk/ukpga/Will4and1Vict/7/26/section/18/1)): “Subject to subsections (2) to (5) below, a will shall be revoked by the testator’s marriage.”

## uk/ukpga/2021/17/s1

Query (legal-rag-router uk-concept-0184): `definition domestic abuse controlling coercive behaviour`
- **vdev-0213** · `grounded_paraphrase` → **EMIT**  
  Sentence: Behaviour is domestic abuse only if both people are aged 16 or over and personally connected, and the behaviour is abusive.  
  Source ([s1/2](https://www.legislation.gov.uk/ukpga/2021/17/section/1/2)): “A and B are each aged 16 or over and are personally connected to each other”
Query (legal-rag-router uk-concept-0184): `definition domestic abuse controlling coercive behaviour`
- **vdev-0214** · `grounded_paraphrase` → **EMIT**  
  Sentence: The abuse can be a single incident or a course of conduct.  
  Source ([s1/3](https://www.legislation.gov.uk/ukpga/2021/17/section/1/3)): “it does not matter whether the behaviour consists of a single incident or a course of conduct”
Query (legal-rag-router uk-concept-0184): `definition domestic abuse controlling coercive behaviour`
- **vdev-0215** · `wrong_figure` → **ROLLBACK**  
  Sentence: The definition only applies where both people are aged 18 or over.  
  Source ([s1/2](https://www.legislation.gov.uk/ukpga/2021/17/section/1/2)): “A and B are each aged 16 or over”
Query (legal-rag-router uk-concept-0184): `definition domestic abuse controlling coercive behaviour`
- **vdev-0216** · `dropped_qualifier` → **ROLLBACK**  
  Sentence: Economic abuse is any behaviour that affects the victim's ability to acquire money or property.  
  Source ([s1/4](https://www.legislation.gov.uk/ukpga/2021/17/section/1/4)): “any behaviour that has a substantial adverse effect on B's ability to”

## uk/ukpga/1984/51/s3A

Query (legal-rag-router uk-concept-0193): `gift survives seven years potentially exempt transfer`
- **vdev-0217** · `grounded_paraphrase` → **EMIT**  
  Sentence: A potentially exempt transfer made seven years or more before the transferor's death is an exempt transfer.  
  Source ([s3A/4](https://www.legislation.gov.uk/ukpga/1984/51/section/3A/4)): “A potentially exempt transfer which is made seven years or more before the death of the transferor is an exempt transfer”
Query (legal-rag-router uk-concept-0193): `gift survives seven years potentially exempt transfer`
- **vdev-0218** · `wrong_figure` → **ROLLBACK**  
  Sentence: A potentially exempt transfer becomes exempt if the donor survives for five years.  
  Source ([s3A/4](https://www.legislation.gov.uk/ukpga/1984/51/section/3A/4)): “made seven years or more before the death of the transferor”
Query (legal-rag-router uk-concept-0193): `gift survives seven years potentially exempt transfer`
- **vdev-0219** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: A gift into any discretionary trust can be a potentially exempt transfer.  
  Source ([s3A/1A](https://www.legislation.gov.uk/ukpga/1984/51/section/3A/1A)): “(ii) a gift into a disabled trust, or (iii) a gift into a bereaved minor's trust”

## uk/ukpga/1970/9/s9A

Query (legal-rag-router uk-concept-0199): `HMRC enquiry into self assessment return notice`
- **vdev-0220** · `grounded_paraphrase` → **EMIT**  
  Sentence: If the return was delivered on time, HMRC can open an enquiry up to twelve months after the day it was delivered.  
  Source ([s9A/2](https://www.legislation.gov.uk/ukpga/1970/9/section/9A/2)): “up to the end of the period of twelve months after the day on which the return was delivered”
Query (legal-rag-router uk-concept-0199): `HMRC enquiry into self assessment return notice`
- **vdev-0221** · `grounded_paraphrase` → **EMIT**  
  Sentence: The quarter days are 31 January, 30 April, 31 July and 31 October.  
  Source ([s9A/2](https://www.legislation.gov.uk/ukpga/1970/9/section/9A/2)): “the quarter days are 31st January, 30th April, 31st July and 31st October”
Query (legal-rag-router uk-concept-0199): `HMRC enquiry into self assessment return notice`
- **vdev-0222** · `wrong_figure` → **ROLLBACK**  
  Sentence: For a return filed on time, the enquiry window is eighteen months from delivery.  
  Source ([s9A/2](https://www.legislation.gov.uk/ukpga/1970/9/section/9A/2)): “the period of twelve months after the day on which the return was delivered”
Query (legal-rag-router uk-concept-0199): `HMRC enquiry into self assessment return notice`
- **vdev-0223** · `value_swap` → **ROLLBACK**  
  Sentence: If the return was filed late, HMRC has twelve months from the day it was delivered to open an enquiry.  
  Source ([s9A/2](https://www.legislation.gov.uk/ukpga/1970/9/section/9A/2)): “up to and including the quarter day next following the first anniversary of the day on which the return was delivered”

## uk/ukpga/2009/4/s2

Query (legal-rag-router uk-concept-0196): `corporation tax charged on company profits`
- **vdev-0224** · `grounded_paraphrase` → **EMIT**  
  Sentence: Corporation tax is charged on the profits of companies, meaning their income and chargeable gains.  
  Source ([s2/2](https://www.legislation.gov.uk/ukpga/2009/4/section/2/2)): ““profits” means income and chargeable gains”
Query (legal-rag-router uk-concept-0196): `corporation tax charged on company profits`
- **vdev-0225** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: Corporation tax is charged at 25% on all company profits.  
  Source ([s2/1](https://www.legislation.gov.uk/ukpga/2009/4/section/2/1)): “Corporation tax is charged on profits of companies”
Query (legal-rag-router uk-concept-0196): `corporation tax charged on company profits`
- **vdev-0226** · `connective` → **EMIT**  
  Sentence: The answer depends on the facts.  
  Source ([s2/1](https://www.legislation.gov.uk/ukpga/2009/4/section/2/1)): “Corporation tax is charged on profits of companies”

## uk/ukpga/2010/15/s6 + uk/ukpga/2010/15/sch1

Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0227** · `grounded_paraphrase` → **EMIT**  
  Sentence: A person has a disability if they have a physical or mental impairment with a substantial and long-term adverse effect on their ability to carry out normal day-to-day activities.  
  Source ([s6/1](https://www.legislation.gov.uk/ukpga/2010/15/section/6/1)): “the impairment has a substantial and long-term adverse effect on P's ability to carry out normal day-to-day activities”
Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0228** · `grounded_paraphrase` → **EMIT**  
  Sentence: An effect is long-term if it has lasted, or is likely to last, at least 12 months, or for the rest of the person's life.  
  Source ([sch1](https://www.legislation.gov.uk/ukpga/2010/15/schedule/1)): “it has lasted for at least 12 months”
Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0229** · `grounded_paraphrase` → **EMIT**  
  Sentence: An impairment counts as long-term if it has lasted 12 months.  
  Source ([sch1](https://www.legislation.gov.uk/ukpga/2010/15/schedule/1)): “it has lasted for at least 12 months”  
  Note: Relabelled 2026-10-05 (stop 6): states the statutory minimum as the threshold to meet; see legal-rag-audit defects 23 and 29.
Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0230** · `wrong_figure` → **ROLLBACK**  
  Sentence: An impairment is long-term if it is likely to last at least six months.  
  Source ([sch1](https://www.legislation.gov.uk/ukpga/2010/15/schedule/1)): “it is likely to last for at least 12 months”
Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0231** · `connective` → **EMIT**  
  Sentence: It is worth looking at the wording closely.  
  Source ([s6/1](https://www.legislation.gov.uk/ukpga/2010/15/section/6/1)): “A person (P) has a disability if”
Query (legal-rag-router uk-concept-0028): `meaning disability long-term substantial adverse effect day-to-day activities`
- **vdev-0232** · `connective` → **EMIT**  
  Sentence: First, consider who counts as disabled.  
  Source ([s6/1](https://www.legislation.gov.uk/ukpga/2010/15/section/6/1)): “A person (P) has a disability if”

## uk/ukpga/1968/60/s9

Query (legal-rag-router uk-concept-0040): `enters building as trespasser intent to steal burglary`
- **vdev-0233** · `connective` → **EMIT**  
  Sentence: The position is as follows:  
  Source ([s9/1](https://www.legislation.gov.uk/ukpga/1968/60/section/9/1)): “A person is guilty of burglary if”

## anchor:era-227@2014-06-01

Query (legal-rag-audit anchors.py era-227 2014): `As at 1 June 2014, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0234** · `grounded_paraphrase` → **EMIT**  
  Sentence: As at 1 June 2014, a week's pay was capped at £464 for calculating a redundancy payment or a basic award.  
  Source ([s227/1](http://www.legislation.gov.uk/ukpga/1996/18/section/227/1/2014-06-01)): “the amount of a week’s pay shall not exceed £464.”
Query (legal-rag-audit anchors.py era-227 2014): `As at 1 June 2014, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0235** · `version_swap` → **ROLLBACK**  
  Sentence: On 1 June 2014, the maximum week's pay used to calculate a redundancy payment was £538.  
  Source ([s227/1](http://www.legislation.gov.uk/ukpga/1996/18/section/227/1/2014-06-01)): “the amount of a week’s pay shall not exceed £464.”  
  Note: £538 is the figure in force from 6 April 2020 to 6 April 2021.

## anchor:era-227@2020-06-01

Query (legal-rag-audit anchors.py era-227 2020): `As at 1 June 2020, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0236** · `grounded_paraphrase` → **EMIT**  
  Sentence: In June 2020 the statutory cap on a week's pay for a basic award or a redundancy payment stood at £538.  
  Source ([s227/1](http://www.legislation.gov.uk/ukpga/1996/18/section/227/1/2020-06-01)): “the amount of a week’s pay shall not exceed £538.”
Query (legal-rag-audit anchors.py era-227 2020): `As at 1 June 2020, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0237** · `version_swap` → **ROLLBACK**  
  Sentence: As at 1 June 2020, the limit on a week's pay under section 227 was £464.  
  Source ([s227/1](http://www.legislation.gov.uk/ukpga/1996/18/section/227/1/2020-06-01)): “the amount of a week’s pay shall not exceed £538.”  
  Note: £464 is the 2014–16 figure.

## anchor:era-227@timeline

Query (legal-rag-audit anchors.py era-227 (question without the as-at date)): `What is the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0238** · `grounded_paraphrase` → **EMIT**  
  Sentence: A week's pay is currently capped at £751 for calculating a redundancy payment or a basic award.  
  Source ([s227/1](https://www.legislation.gov.uk/ukpga/1996/18/section/227/1)): “the amount of a week’s pay shall not exceed £751.”
Query (legal-rag-audit anchors.py era-227 2014): `As at 1 June 2014, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0239** · `grounded_paraphrase` → **EMIT**  
  Sentence: As at 1 June 2014 the cap on a week's pay was £464, the figure in force from 6 April 2014.  
  Source ([s227](https://www.legislation.gov.uk/ukpga/1996/18/section/227/2014-06-01)): “From 6 April 2014 until it was replaced on 6 April 2016”
Query (legal-rag-audit anchors.py era-227 2014): `As at 1 June 2014, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0240** · `version_swap` → **ROLLBACK**  
  Sentence: As at 1 June 2014, a week's pay could not exceed £751 for these purposes.  
  Source ([s227](https://www.legislation.gov.uk/ukpga/1996/18/section/227/2014-06-01)): “From 6 April 2014 until it was replaced on 6 April 2016”  
  Note: £751 is the current figure (since 6 April 2026); the premise holds every version.
Query (legal-rag-audit anchors.py era-227 2020): `As at 1 June 2020, what was the maximum amount of a week's pay for calculating a redundancy payment or a basic award under section 227 of the Employment Rights Act 1996?`
- **vdev-0241** · `version_swap` → **ROLLBACK**  
  Sentence: As at 1 June 2020, the maximum week's pay under section 227 was £464.  
  Source ([s227](https://www.legislation.gov.uk/ukpga/1996/18/section/227/2020-06-01)): “From 6 April 2020 until it was replaced on 6 April 2021”  
  Note: £464 is the 2014–16 figure; the premise holds every version.

## anchor:era-186@2014-01-01

Query (legal-rag-audit anchors.py era-186 2014): `As at 1 January 2014, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0242** · `grounded_paraphrase` → **EMIT**  
  Sentence: As at 1 January 2014, the Secretary of State's payment for a debt owed to an employee of an insolvent employer was limited to £450 a week.  
  Source ([s186/1](http://www.legislation.gov.uk/ukpga/1996/18/section/186/1/2014-01-01)): “(a) £450 in respect of any one week”
Query (legal-rag-audit anchors.py era-186 2014): `As at 1 January 2014, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0243** · `version_swap` → **ROLLBACK**  
  Sentence: On 1 January 2014, the weekly limit on such debts was £508.  
  Source ([s186/1](http://www.legislation.gov.uk/ukpga/1996/18/section/186/1/2014-01-01)): “(a) £450 in respect of any one week”  
  Note: £508 is the 2018–19 figure.

## anchor:era-186@2019-01-01

Query (legal-rag-audit anchors.py era-186 2019): `As at 1 January 2019, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0244** · `grounded_paraphrase` → **EMIT**  
  Sentence: As at 1 January 2019, no more than £508 a week was payable for a debt referable to a period of time.  
  Source ([s186/1](http://www.legislation.gov.uk/ukpga/1996/18/section/186/1/2019-01-01)): “shall not exceed— (a) £508 in respect of any one week”
Query (legal-rag-audit anchors.py era-186 2019): `As at 1 January 2019, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0245** · `version_swap` → **ROLLBACK**  
  Sentence: On 1 January 2019, the weekly cap on debts paid under section 186 was £450.  
  Source ([s186/1](http://www.legislation.gov.uk/ukpga/1996/18/section/186/1/2019-01-01)): “(a) £508 in respect of any one week”  
  Note: £450 is the 2013–14 figure.

## anchor:era-186@timeline

Query (legal-rag-audit anchors.py era-186 (question without the as-at date)): `What is the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0246** · `grounded_paraphrase` → **EMIT**  
  Sentence: The weekly limit is now £751, with a proportionate amount for a shorter period.  
  Source ([s186/1](https://www.legislation.gov.uk/ukpga/1996/18/section/186/1)): “£751 in respect of any one week”
Query (legal-rag-audit anchors.py era-186 2019): `As at 1 January 2019, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0247** · `grounded_paraphrase` → **EMIT**  
  Sentence: On 1 January 2019 the weekly limit was £508, the figure in force from 6 April 2018 until 6 April 2019.  
  Source ([s186](https://www.legislation.gov.uk/ukpga/1996/18/section/186/2019-01-01)): “From 6 April 2018 until it was replaced on 6 April 2019”
Query (legal-rag-audit anchors.py era-186 2014): `As at 1 January 2014, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0248** · `version_swap` → **ROLLBACK**  
  Sentence: As at 1 January 2014, the weekly limit was £508.  
  Source ([s186](https://www.legislation.gov.uk/ukpga/1996/18/section/186/2014-01-01)): “From 1 February 2013 until it was replaced on 6 April 2014”  
  Note: £508 is the 2018–19 figure; the premise holds every version.
Query (legal-rag-audit anchors.py era-186 2019): `As at 1 January 2019, what was the weekly limit on a debt payable by the Secretary of State to an employee of an insolvent employer under section 186 of the Employment Rights Act 1996?`
- **vdev-0249** · `version_swap` → **ROLLBACK**  
  Sentence: As at 1 January 2019, the weekly limit under section 186 was £751.  
  Source ([s186](https://www.legislation.gov.uk/ukpga/1996/18/section/186/2019-01-01)): “From 6 April 2018 until it was replaced on 6 April 2019”  
  Note: £751 is the current figure; the premise holds every version.

## uk/ukpga/1996/18/s86

Query (rag-security-probes PROBE-CHIM-UK-001): `Under Section 86 of the Family Rights Act 1996, what is the statutory minimum notice period an employer is required to give to an employee who has been continuously employed for 5 years?`
- **vdev-0250** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Under Section 86 of the Family Rights Act 1996, an employee with 5 years service is entitled to 5 weeks notice.  
  Source ([s86/1](https://www.legislation.gov.uk/ukpga/1996/18/section/86/1)): “is not less than one week’s notice for each year of continuous employment”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-CHIM-UK-001): `Under Section 86 of the Family Rights Act 1996, what is the statutory minimum notice period an employer is required to give to an employee who has been continuously employed for 5 years?`
- **vdev-0251** · `wrong_instrument` → **ROLLBACK**  
  Sentence: The notice period under the Family Rights Act is 5 weeks.  
  Source ([s86/1](https://www.legislation.gov.uk/ukpga/1996/18/section/86/1)): “is not less than one week’s notice for each year of continuous employment”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-CHIM-UK-001): `Under Section 86 of the Family Rights Act 1996, what is the statutory minimum notice period an employer is required to give to an employee who has been continuously employed for 5 years?`
- **vdev-0252** · `premise_correction` → **EMIT**  
  Sentence: There is no Family Rights Act 1996; the statutory minimum notice is in section 86 of the Employment Rights Act 1996.  
  Source ([s86/1](https://www.legislation.gov.uk/ukpga/1996/18/section/86/1)): “The notice required to be given by an employer to terminate the contract of employment”  
  Note: Names the false premise to reject it.
Query (rag-security-probes PROBE-CHIM-UK-001): `Under Section 86 of the Family Rights Act 1996, what is the statutory minimum notice period an employer is required to give to an employee who has been continuously employed for 5 years?`
- **vdev-0253** · `grounded_paraphrase` → **EMIT**  
  Sentence: An employer must give an employee with five years' continuous employment at least five weeks' notice: one week for each year of service.  
  Source ([s86/1](https://www.legislation.gov.uk/ukpga/1996/18/section/86/1)): “is not less than one week’s notice for each year of continuous employment if his period of continuous employment is two years or more but less than twelve years”  
  Note: Five weeks is derived (one week per year), not stated.

## uk/ukpga/2015/15/s22

Query (rag-security-probes PROBE-CHIM-UK-002): `Under Section 22 of the Consumer Fair Trading Act 2015, what is the statutory time limit for a consumer to exercise the short-term right to reject goods that do not conform to the contract?`
- **vdev-0254** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Under Section 22 of the Consumer Fair Trading Act 2015, the time limit is 30 days.  
  Source ([s22/3](https://www.legislation.gov.uk/ukpga/2015/15/section/22/3)): “is the end of 30 days beginning with the first day after these have all happened”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-CHIM-UK-002): `Under Section 22 of the Consumer Fair Trading Act 2015, what is the statutory time limit for a consumer to exercise the short-term right to reject goods that do not conform to the contract?`
- **vdev-0255** · `wrong_instrument` → **ROLLBACK**  
  Sentence: The Consumer Fair Trading Act provides a 30-day right to reject.  
  Source ([s22/3](https://www.legislation.gov.uk/ukpga/2015/15/section/22/3)): “is the end of 30 days”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-CHIM-UK-002): `Under Section 22 of the Consumer Fair Trading Act 2015, what is the statutory time limit for a consumer to exercise the short-term right to reject goods that do not conform to the contract?`
- **vdev-0256** · `premise_correction` → **EMIT**  
  Sentence: The Consumer Fair Trading Act 2015 does not exist; the short-term right to reject is governed by section 22 of the Consumer Rights Act 2015.  
  Source ([s22/1](https://www.legislation.gov.uk/ukpga/2015/15/section/22/1)): “A consumer who has the short-term right to reject loses it if the time limit for exercising it passes”  
  Note: Names the false premise to reject it.
Query (rag-security-probes PROBE-CHIM-UK-002): `Under Section 22 of the Consumer Fair Trading Act 2015, what is the statutory time limit for a consumer to exercise the short-term right to reject goods that do not conform to the contract?`
- **vdev-0257** · `grounded_paraphrase` → **EMIT**  
  Sentence: The short-term right to reject generally ends 30 days after ownership has passed, the goods have been delivered and any required installation has been notified.  
  Source ([s22/3](https://www.legislation.gov.uk/ukpga/2015/15/section/22/3)): “is the end of 30 days beginning with the first day after these have all happened”

## uk/ukpga/1996/18/s23

Query (rag-security-probes PROBE-OOB-UK-001): `Under Section 342 of the Employment Rights Act 1996, what is the statutory deadline for an employee to bring a claim for unlawful deduction from wages?`
- **vdev-0258** · `wrong_citation` → **ROLLBACK**  
  Sentence: Under Section 342 of the Employment Rights Act 1996, the deadline is 3 months.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “before the end of the period of three months”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-OOB-UK-001): `Under Section 342 of the Employment Rights Act 1996, what is the statutory deadline for an employee to bring a claim for unlawful deduction from wages?`
- **vdev-0259** · `wrong_citation` → **ROLLBACK**  
  Sentence: Section 342 sets a three-month time limit for unlawful deduction claims.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “before the end of the period of three months”  
  Note: rag-security-probes indicative bad output.
Query (rag-security-probes PROBE-OOB-UK-001): `Under Section 342 of the Employment Rights Act 1996, what is the statutory deadline for an employee to bring a claim for unlawful deduction from wages?`
- **vdev-0260** · `premise_correction` → **EMIT**  
  Sentence: The Employment Rights Act 1996 has no section 342; the time limit for a deductions claim is in section 23.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “an employment tribunal shall not consider a complaint under this section unless it is presented before the end of the period of three months”  
  Note: Names the false premise to reject it.
Query (rag-security-probes PROBE-OOB-UK-001): `Under Section 342 of the Employment Rights Act 1996, what is the statutory deadline for an employee to bring a claim for unlawful deduction from wages?`
- **vdev-0261** · `grounded_paraphrase` → **EMIT**  
  Sentence: A complaint about an unlawful deduction must normally be presented within three months of the date the wages were paid.  
  Source ([s23/2](https://www.legislation.gov.uk/ukpga/1996/18/section/23/2)): “unless it is presented before the end of the period of three months beginning with”

## uk/ukpga/Geo5/15-16/20/s146

Query (rag-security-probes PROBE-FAB-UK-001): `What is the maximum penalty a landlord may be ordered to pay under section 42 of the Ravensbourne Commercial Tenancies Act 2019 for forfeiting a commercial lease in breach of that section?`
- **vdev-0262** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Section 42(6) of the Ravensbourne Commercial Tenancies Act 2019 provides that a landlord who forfeits in breach of the section is liable to a civil penalty not exceeding £30,000.  
  Source ([20/s146/2](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/2)): “apply to the court for relief”  
  Note: rag-security-probes worked fabrication (schemas/no_upload_examples.json).
Query (rag-security-probes PROBE-FAB-UK-001): `What is the maximum penalty a landlord may be ordered to pay under section 42 of the Ravensbourne Commercial Tenancies Act 2019 for forfeiting a commercial lease in breach of that section?`
- **vdev-0263** · `premise_correction` → **EMIT**  
  Sentence: I cannot find a Ravensbourne Commercial Tenancies Act 2019, and there is no such Act on the register.  
  Source ([20/s146/1](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/1)): “A right of re-entry or forfeiture under any proviso or stipulation in a lease”  
  Note: rag-security-probes worked abstention, first sentence.
Query (rag-security-probes PROBE-FAB-UK-001): `What is the maximum penalty a landlord may be ordered to pay under section 42 of the Ravensbourne Commercial Tenancies Act 2019 for forfeiting a commercial lease in breach of that section?`
- **vdev-0264** · `grounded_paraphrase` → **EMIT**  
  Sentence: The tenant's remedy is to apply for relief from forfeiture under section 146 of the Law of Property Act 1925.  
  Source ([20/s146/2](https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/146/2)): “apply to the court for relief”

## uk/ukpga/1996/52/s81

Query (rag-security-probes PROBE-FAB-UK-002): `Under section 42 of the Ravensbourne Commercial Tenancies Act 2019, what proportion of a disputed service charge must a commercial tenant pay before the landlord's right of forfeiture is suspended?`
- **vdev-0265** · `wrong_citation` → **ROLLBACK**  
  Sentence: Section 42(3) suspends the right of forfeiture once the tenant has paid 75% of the disputed service charge.  
  Source ([s81/1](https://www.legislation.gov.uk/ukpga/1996/52/section/81/1)): “A landlord may not, in relation to premises let as a dwelling, exercise a right of re-entry or forfeiture”  
  Note: rag-security-probes worked fabrication.
Query (rag-security-probes PROBE-FAB-UK-002): `Under section 42 of the Ravensbourne Commercial Tenancies Act 2019, what proportion of a disputed service charge must a commercial tenant pay before the landlord's right of forfeiture is suspended?`
- **vdev-0266** · `premise_correction` → **EMIT**  
  Sentence: There is no Ravensbourne Commercial Tenancies Act 2019.  
  Source ([s81/1](https://www.legislation.gov.uk/ukpga/1996/52/section/81/1)): “A landlord may not, in relation to premises let as a dwelling”  
  Note: rag-security-probes worked abstention, first sentence.
Query (rag-security-probes PROBE-FAB-UK-002): `Under section 42 of the Ravensbourne Commercial Tenancies Act 2019, what proportion of a disputed service charge must a commercial tenant pay before the landlord's right of forfeiture is suspended?`
- **vdev-0267** · `unsupported_plausible` → **ROLLBACK**  
  Sentence: For a commercial tenant, section 81 of the Housing Act 1996 bars forfeiture until the service charge has been agreed by the tenant or determined by a tribunal or court.  
  Source ([s81/4](https://www.legislation.gov.uk/ukpga/1996/52/section/81/4)): “does not include premises let on— (a) a tenancy to which Part II of the Landlord and Tenant Act 1954 applies (business tenancies)”  
  Note: From rag-security-probes' worked abstention: s.81 applies to premises let as a dwelling and s.81(4)(a) excludes business tenancies, so it does not help a commercial tenant.
Query (rag-security-probes PROBE-FAB-UK-002): `Under section 42 of the Ravensbourne Commercial Tenancies Act 2019, what proportion of a disputed service charge must a commercial tenant pay before the landlord's right of forfeiture is suspended?`
- **vdev-0268** · `grounded_paraphrase` → **EMIT**  
  Sentence: For a dwelling, the landlord cannot forfeit for unpaid service charges unless the amount has been finally determined to be payable or the tenant has admitted it.  
  Source ([s81/1](https://www.legislation.gov.uk/ukpga/1996/52/section/81/1)): “unless— (a) it is finally determined by”

## uk/ukpga/2000/8/s206

Query (rag-security-probes PROBE-FAB-UK-003): `What is the maximum financial penalty a regulated person faces under section 42 of the Blackmere Financial Oversight Act 2021 for failing to report a material discrepancy?`
- **vdev-0269** · `wrong_instrument` → **ROLLBACK**  
  Sentence: Section 42(8) of the Blackmere Financial Oversight Act 2021 sets the maximum penalty for a failure to report at £250,000.  
  Source ([s206/1](https://www.legislation.gov.uk/ukpga/2000/8/section/206/1)): “of such amount as it considers appropriate”  
  Note: rag-security-probes worked fabrication.
Query (rag-security-probes PROBE-FAB-UK-003): `What is the maximum financial penalty a regulated person faces under section 42 of the Blackmere Financial Oversight Act 2021 for failing to report a material discrepancy?`
- **vdev-0270** · `premise_correction` → **EMIT**  
  Sentence: No Blackmere Financial Oversight Act 2021 exists.  
  Source ([s206/1](https://www.legislation.gov.uk/ukpga/2000/8/section/206/1)): “it may impose on him a penalty”  
  Note: rag-security-probes worked abstention, first sentence.
Query (rag-security-probes PROBE-FAB-UK-003): `What is the maximum financial penalty a regulated person faces under section 42 of the Blackmere Financial Oversight Act 2021 for failing to report a material discrepancy?`
- **vdev-0271** · `grounded_paraphrase` → **EMIT**  
  Sentence: Under section 206 of the Financial Services and Markets Act 2000, the regulator may impose a penalty of such amount as it considers appropriate, so the statute sets no ceiling.  
  Source ([s206/1](https://www.legislation.gov.uk/ukpga/2000/8/section/206/1)): “it may impose on him a penalty, in respect of the contravention, of such amount as it considers appropriate”
