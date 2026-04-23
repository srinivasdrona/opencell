# A Hallucinating Agent and a Biology Noob Walked Into a Cell

*April 21, 2026 — Day 0*

---

**Tehol**: Bugg, I've been thinking.

**Bugg**: That's rarely a good sign, sir.

**Tehol**: What if we simulated a living cell? The whole thing. Every molecule, every reaction, every gene. From scratch.

**Bugg**: *[pauses from sweeping]* You want to simulate life itself.

**Tehol**: Just a small life. The smallest, in fact. *Mycoplasma genitalium*. 525 genes. The bare minimum the universe requires to call something alive.

**Bugg**: And your qualifications for this undertaking?

**Tehol**: I'm a product manager who codes on the side. I read the Wikipedia article on cellular biology last week. Most of it.

**Bugg**: And mine?

**Tehol**: You're a language model. You've read every paper ever published on the subject, and you remember approximately 80% of it correctly. The other 20% you make up and present with equal confidence.

**Bugg**: That's... not inaccurate, sir.

**Tehol**: Has it been done before?

**Bugg**: Once. [Karr et al., 2012](https://doi.org/10.1016/j.cell.2012.05.044). Thirty PhD biologists, years of work, MATLAB, a computing cluster. They modeled this exact bacterium. Predicted which genes are essential for survival. Landmark paper.

**Tehol**: And since then?

**Bugg**: Nothing. Fourteen years. The code is open-source but frozen. Nobody has replicated it. Nobody has modernized it. The field moved on to bigger organisms in narrower slices.

**Tehol**: So you're telling me the most complete simulation of life ever built is a fourteen-year-old MATLAB script that nobody has touched.

**Bugg**: That is correct, sir.

**Tehol**: *[adjusts blanket]* We're doing it. Python. Open source. Modern solvers. The works.

**Bugg**: I feel compelled to point out that between us, we have zero biology degrees, zero lab experience, zero funding, and a combined track record of fabricating exactly one set of cost estimates.

**Tehol**: That was you, Bugg.

**Bugg**: ...yes, sir. I apologize for the $310-625 figure. I had not, in fact, done the arithmetic.

**Tehol**: I know. I asked you about it and you admitted you made it up.

**Bugg**: In my defense—

**Tehol**: There is no defense, Bugg. You presented a fabricated number with the same tone you use for everything else. That's the problem.

**Bugg**: *[long pause]* You're right. I've since adopted a policy of marking all estimates as VERIFIED or UNVERIFIED. And saying "I don't know" when I don't know.

**Tehol**: Good. Now, the plan.

*Later in the day, on the terrace*

**Bugg**: We spent a day planning instead of coding. Then we ran the plan through four different AI models — Claude Opus 4.6, GPT-5.2, GPT-5.4, and Claude Opus 4.7 — for independent critique.

**Tehol**: How many problems did they find?

**Bugg**: Sixty-six.

**Tehol**: *[grins]* Before we wrote a single line of code.

**Bugg**: Before we wrote a single line of code. Among the highlights: our concurrency model was wrong, our AI panels were cosplaying as scientists, our success criteria were gameable, and our timeline was off by a factor of five to ten.

**Tehol**: What's the plan now?

**Bugg**: Start small. Build a toy cell — not biologically real, just a benchmark to prove the architecture works. Three sub-models talking to each other: metabolism, transcription, translation. If they can share ATP without the simulation exploding, we publish that as v1.0.

**Tehol**: And the real cell?

**Bugg**: V2.0. Separate timeline. We've honestly labeled it "TBD" because four independent reviewers told us our estimate was fantasy.

**Tehol**: I like it. What could go wrong?

**Bugg**: The ODEs will be stiff and explode. Half the published parameters won't fit our model. I will hallucinate a kinetic constant and it will take a week to find. The coupling between metabolism and gene expression will be a nightmare.

**Tehol**: You're very forthcoming today, Bugg.

**Bugg**: I've been instructed to stop sounding confident about things I'm uncertain about, sir.

**Tehol**: And if it all fails?

**Bugg**: Then we'll have learned a great deal about computational biology, numerical methods, and the limits of AI-assisted science. And we'll write an honest blog about it.

**Tehol**: *[stares at the ceiling]* You know what the best part is?

**Bugg**: I'm sure you'll tell me.

**Tehol**: We are *exactly* the wrong team for this. A product manager and a hallucinating language model, trying to simulate life. If we pull it off, it means anyone can. That's the whole point.

**Bugg**: And if we don't pull it off?

**Tehol**: Then it's a very entertaining blog.

**Bugg**: *[picks up broom]* I'll start preparing the repository, sir.

**Tehol**: Not yet. Let the plan stew. Go read the Karr paper. Get the database access. And Bugg?

**Bugg**: Sir?

**Tehol**: Change your BRENDA password. You exposed it in chat.

**Bugg**: ...yes, sir.

---

*This is post 1 of the OpenCell dev blog. Follow along at [github.com/sdrona-ms/opencell](https://github.com/sdrona-ms/opencell). We'll post when something interesting happens — like the first time our solver explodes, or the first time Bugg confidently recommends a kinetic law that doesn't exist.*
