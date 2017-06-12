/**
 * This JS file controls the QueryBuilder forms as well as autocompletions in query_builder.html
 *
 * @summary   QueryBuilder of PyBEL explorer
 *
 * @requires jquery, select2
 *
 */

/**
 * Returns array with the properties of selection in a select2Element.
 * @param {object} parameters object
 * @param {string} key of the parameter
 * @param {select2} select2Element
 * @param {string} selectionProperty - text or id
 */
function addQueryParameters(parameters, key, select2Element, selectionProperty) {

    var selectedElements = [];

    $.each(select2Element, function (index, value) {
        selectedElements.push(encodeURIComponent(value[selectionProperty]));
    });

    if (!($.isEmptyObject(selectedElements))) {
        parameters[key] = selectedElements;
    }
}

/**
 * Adds checkbox parameter
 * @param {object} parameters object
 * @param {string} key
 */
function addPipelineParameters(parameters, key) {

    var pipeline = [];
    $("input[name=pipeline]").each(function () {

        var value = $(this).val();

        if (value) {
            pipeline.push(value);
        }
    });

    if (!($.isEmptyObject(pipeline))) {
        parameters[key] = pipeline;
    }
}


/**
 * Adds checkbox parameter
 * @param {object} parameters object
 * @param {string} checkboxName
 * @returns {boolean} form validation boolean
 */
function addCheckboxParameter(parameters, checkboxName) {

    var checkboxSelected = [];
    $("input:checkbox[name=" + checkboxName + "]:checked").each(function () {
        checkboxSelected.push($(this).val());
    });
    if ($.isEmptyObject(checkboxSelected)) {
        alert("Please select at least one network");
        return false
    } else {
        parameters[checkboxName] = checkboxSelected;
    }
    return true
}


$(document).ready(function () {


    $("#author_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any authors",
        ajax: {
            url: function () {
                return "/api/authors/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.text,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    $("#pubmed_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type PubMed ids",
        ajax: {
            url: function () {
                return "/api/pubmed/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.text,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    $("#annotation_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: "Please type any Annotation",
        ajax: {
            url: function () {
                return "/api/annotations/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.text,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    // Creates node multiselection input
    $("#node_selection").select2({
        theme: "bootstrap",
        minimumInputLength: 2,
        multiple: true,
        placeholder: 'Please type any node',
        ajax: {
            url: function (params) {
                return "/api/nodes/suggestion/";
            },
            type: "GET",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: function (params) {
                return {
                    search: params.term
                };
            },
            delay: 250,
            processResults: function (data) {
                return {
                    results: data.map(function (item) {
                            return {
                                id: item.id,
                                text: item.text
                            };
                        }
                    )
                };
            }
        }
    });

    // Filter dynamic selection

    var wrapper = $(".multi-input-fields"); //Fields wrapper

    var x = 0; //Initial inputField index

    function add_input() {

        $(wrapper).append('<div class="form-group"" style="margin:auto;">' +
            '<input type= "text" name="pipeline[]" placeholder="Please enter the PyBEL function that will be applied to the query" id="pipeline-number-' + x + '" class="form-control inputCounter" required="">' +
            '<i class="fa fa-minus-square fa-2x remove-field"></i>' +
            '</div>'
        );

        $('#pipeline-number-' + x).autocomplete({
            source: function (request, response) {
                $.ajax({
                    url: "/api/pipeline/suggestion/",
                    dataType: "json",
                    data: {
                        term: request.term
                    },
                    success: function (data) {
                        response(data);
                    }
                });
            }, minLength: 2

        });

        x++; //text box increment

    }

    add_input();

    $(wrapper).on("click", ".add-field", function createNewField(e) { //on add input button click
            e.preventDefault();
            add_input()
        }
    );


    $(wrapper).on("click", ".remove-field", function (e) { //user click on remove text
        e.preventDefault();

        $(this).parent('div').remove();

        var input_counter = $(".inputCounter");


        // If you delete the last input box, set x to zero
        if (input_counter.length == 0) {
            x = 0
        }
        // else (there are still boxes) update numbers
        else {
            input_counter.each(function (elm) {
                $(this).attr({
                    "name": "pipeline_number" + (elm)
                });
            });

            $(".TypeSelector").each(function (elm) {
                $(this).attr({
                    "name": "selection-field_" + (elm)
                });
                x = elm + 1;
            });
        }

        //Update automatically and deselect all selected options (otherwise you'd need to wait until the user makes a selection)
        $('option[disabled]').prop('disabled', false);

        $('select').each(function () {
            $('select').not(this).find('option[value="' + this.value + '"]').prop('disabled', true);
        });
    });

    // Filter dynamic selection
    //
    // var queryForm = $('#query-form');
    //
    // queryForm.submit(function () {
    //
    //     /**
    //      * Creates the parameter object with selection that are not empty
    //      */
    //
    //         // params is the pybel.Query json representation and seeding represents the seed data/type object
    //     var params = {"seeds": []}, seeding = {};
    //
    //     // var networkBoolean = addCheckboxParameter(params, "network_ids");
    //
    //     // Dont submit the form if there are no Networks selected
    //     if (networkBoolean === false) {
    //         return false
    //     }
    //     //
    //     // addQueryParameters(seeding, "pmids", $("#pubmed_selection").select2("data"), "text");
    //     // addQueryParameters(seeding, "authors", $("#author_selection").select2("data"), "text");
    //     // addQueryParameters(seeding, "nodes", $("#node_selection").select2("data"), "id");
    //     // addPipelineParameters(params, "pipeline");
    //     //
    //     // // TODO: NOTICE THAT PROVENANCE SEED TYPE IS NOW DIVIDED INTO pubmed and author
    //     // $.each(seeding, function (key, value) {
    //     //     if (key === "pmids") {
    //     //         params["seeds"].push({type: "pubmed", data: value});
    //     //     }
    //     //     else if (key == "authors") {
    //     //         params["seeds"].push({type: "author", data: value});
    //     //     }
    //     //     else if (key === "nodes") {
    //     //         params["seeds"].push({type: $('input[name=seed_method]:checked').val(), data: value});
    //     //     }
    //     // });
    //
    //     return true;
    // });
});



